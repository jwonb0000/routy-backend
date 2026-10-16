# 요청 횟수 제한: 같은 IP·같은 계정에서 짧은 시간에 너무 많이 시도하면 막는다.
# 기록은 서버 메모리에만 있어서 서버를 재시작하면 초기화된다.

import math
import threading
import time
from collections import deque
from collections.abc import Hashable

from fastapi import Depends, Request

from app.config import (
    CHECK_USERNAME_RATE_LIMIT,
    EMAIL_DAILY_RATE_LIMIT,
    EMAIL_RATE_LIMIT,
    LOGIN_FAILURE_WINDOW_MINUTES,
    LOGIN_RATE_LIMIT,
    MAX_LOGIN_FAILURES_PER_IP,
    MAX_PASSWORD_CHECK_FAILURES,
    PASSWORD_CHECK_WINDOW_MINUTES,
    VERIFY_RATE_LIMIT,
)
from app.errors import AppError, ErrorCode

SWEEP_EVERY = 1000


# '최근 N초 동안 몇 번 했는지' 세는 계수기
class SlidingWindowLimiter:
    def __init__(self):
        self._events: dict[Hashable, deque[float]] = {}
        self._windows: dict[Hashable, float] = {}
        self._lock = threading.RLock()
        self._adds = 0

    def _prune(self, key: Hashable, now: float) -> deque[float] | None:
        events = self._events.get(key)
        if events is None:
            return None
        window = self._windows[key]
        while events and events[0] <= now - window:
            events.popleft()
        if not events:
            del self._events[key]
            del self._windows[key]
            return None
        return events

    def retry_after(self, key: Hashable, limit: int, window_seconds: float) -> int | None:
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            if events is not None and len(events) >= limit:
                return max(1, math.ceil(events[0] + window_seconds - now))
            return None

    def add(self, key: Hashable, window_seconds: float) -> None:
        with self._lock:
            now = time.monotonic()
            self._events.setdefault(key, deque()).append(now)
            self._windows[key] = window_seconds
            self._adds += 1
            if self._adds % SWEEP_EVERY == 0:
                for existing_key in list(self._events):
                    self._prune(existing_key, now)

    def hit(self, key: Hashable, limit: int, window_seconds: float) -> int | None:
        with self._lock:
            retry_after = self.retry_after(key, limit, window_seconds)
            if retry_after is None:
                self.add(key, window_seconds)
            return retry_after

    def clear(self, key: Hashable) -> None:
        with self._lock:
            self._events.pop(key, None)
            self._windows.pop(key, None)

    def clear_where(self, matches) -> None:
        with self._lock:
            for key in [key for key in self._events if matches(key)]:
                self.clear(key)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._windows.clear()
            self._adds = 0


limiter = SlidingWindowLimiter()


# API별 요청 횟수 제한 (IP 기준)
def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit: int, window_seconds: int):
    def dependency(request: Request) -> None:
        retry_after = limiter.hit(("rate", bucket, client_ip(request)), limit, window_seconds)
        if retry_after is not None:
            raise AppError(ErrorCode.RATE_LIMITED, extra={"retry_after": retry_after})

    return Depends(dependency)


CHECK_USERNAME_LIMITS = [rate_limit("check-username", *CHECK_USERNAME_RATE_LIMIT)]
EMAIL_SEND_LIMITS = [
    rate_limit("email", *EMAIL_RATE_LIMIT),
    rate_limit("email-daily", *EMAIL_DAILY_RATE_LIMIT),
]
VERIFY_LIMITS = [rate_limit("verify", *VERIFY_RATE_LIMIT)]
LOGIN_LIMITS = [rate_limit("login", *LOGIN_RATE_LIMIT)]

# 로그인 실패 제한 (아이디+IP 기준)
LOGIN_FAILURE_WINDOW_SECONDS = LOGIN_FAILURE_WINDOW_MINUTES * 60


def _login_failure_key(request: Request, username: str) -> tuple:
    return ("login-failure", username, client_ip(request))


def ensure_login_not_blocked(request: Request, username: str) -> None:
    retry_after = limiter.retry_after(
        _login_failure_key(request, username),
        MAX_LOGIN_FAILURES_PER_IP,
        LOGIN_FAILURE_WINDOW_SECONDS,
    )
    if retry_after is not None:
        raise AppError(ErrorCode.TOO_MANY_LOGIN_ATTEMPTS, extra={"retry_after": retry_after})


def record_login_failure(request: Request, username: str) -> None:
    limiter.add(_login_failure_key(request, username), LOGIN_FAILURE_WINDOW_SECONDS)
    ensure_login_not_blocked(request, username)


def clear_login_failures(request: Request, username: str) -> None:
    limiter.clear(_login_failure_key(request, username))


def clear_all_login_failures(username: str) -> None:
    limiter.clear_where(lambda key: key[:2] == ("login-failure", username))


# 현재 비밀번호 확인 실패 제한 (비밀번호 변경·탈퇴 시, 계정 기준)
PASSWORD_CHECK_WINDOW_SECONDS = PASSWORD_CHECK_WINDOW_MINUTES * 60


def _password_check_key(user_id: int) -> tuple:
    return ("password-check", user_id)


def ensure_password_check_allowed(user_id: int) -> None:
    retry_after = limiter.retry_after(
        _password_check_key(user_id),
        MAX_PASSWORD_CHECK_FAILURES,
        PASSWORD_CHECK_WINDOW_SECONDS,
    )
    if retry_after is not None:
        raise AppError(ErrorCode.TOO_MANY_PASSWORD_ATTEMPTS, extra={"retry_after": retry_after})


def record_password_check_failure(user_id: int) -> None:
    limiter.add(_password_check_key(user_id), PASSWORD_CHECK_WINDOW_SECONDS)
    ensure_password_check_allowed(user_id)


def clear_password_check_failures(user_id: int) -> None:
    limiter.clear(_password_check_key(user_id))
