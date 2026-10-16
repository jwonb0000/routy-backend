# 보안 도구 모음: 비밀번호 암호화, 로그인 토큰(JWT) 발급·검사, 인증 코드 생성.

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    BCRYPT_ROUNDS,
    JWT_ALGORITHM,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    REMEMBER_ME_EXPIRE_DAYS,
    SECRET_KEY,
)
from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models import User

ACCESS_TOKEN_TYPE = "access"
PASSWORD_RESET_TOKEN_TYPE = "password_reset"

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: User
    remember_me: bool


# 비밀번호 암호화(bcrypt)와 확인
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    encoded = plain_password.encode("utf-8")
    if len(encoded) > 72:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))


# 토큰 공통 처리 (만들기 / 풀기 / 사용자 번호 꺼내기)
def _encode(claims: dict, lifetime: timedelta) -> str:
    payload = {**claims, "exp": datetime.now(timezone.utc) + lifetime}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def _user_id(payload: dict | None) -> int | None:
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


# 토큰 발급: 로그인용, 비밀번호 재설정용
def create_access_token(user: User, remember_me: bool = False) -> tuple[str, int]:
    lifetime = (
        timedelta(days=REMEMBER_ME_EXPIRE_DAYS)
        if remember_me
        else timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    claims = {
        "sub": str(user.id),
        "type": ACCESS_TOKEN_TYPE,
        "ver": user.token_version,
        "rm": remember_me,
    }
    return _encode(claims, lifetime), int(lifetime.total_seconds())


def create_password_reset_token(user: User) -> tuple[str, int]:
    lifetime = timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    claims = {"sub": str(user.id), "type": PASSWORD_RESET_TOKEN_TYPE}
    return _encode(claims, lifetime), int(lifetime.total_seconds())


def read_password_reset_token(token: str) -> int:
    user_id = _user_id(_decode(token, PASSWORD_RESET_TOKEN_TYPE))
    if user_id is None:
        raise AppError(ErrorCode.INVALID_RESET_TOKEN)
    return user_id


# 로그인 확인: 요청 헤더의 토큰으로 현재 사용자를 찾는다 (로그인이 필요한 API에서 사용)
def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    if credentials is None:
        raise AppError(ErrorCode.UNAUTHORIZED)

    payload = _decode(credentials.credentials, ACCESS_TOKEN_TYPE)
    user_id = _user_id(payload)
    user = db.get(User, user_id) if user_id is not None else None

    if user is None or payload.get("ver") != user.token_version:
        raise AppError(ErrorCode.INVALID_TOKEN)

    return AuthContext(user=user, remember_me=bool(payload.get("rm")))


def get_current_user(auth: AuthContext = Depends(get_auth_context)) -> User:
    return auth.user


# 지금까지 발급한 로그인 토큰을 전부 무효화 (비밀번호 변경·재설정 시)
def revoke_all_tokens(user: User) -> None:
    user.token_version += 1


# 6자리 인증 코드 생성·비교, 시간대 보정
def generate_verification_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def codes_match(expected: str, given: str) -> bool:
    return secrets.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
