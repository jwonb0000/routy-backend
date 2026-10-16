# 설정 모음: .env 값을 읽고, 서비스 전체에서 쓰는 숫자(만료 시간, 시도 제한 등)를 한곳에 둔다.
# 규칙을 바꾸고 싶으면 대부분 이 파일의 숫자만 고치면 된다.

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 필수 비밀 값과 메일 설정 (.env에서 읽음)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(".env에 SECRET_KEY가 없습니다")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY는 32자 이상이어야 합니다")

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "smtp").strip().lower()
if EMAIL_BACKEND not in ("smtp", "console"):
    raise RuntimeError("EMAIL_BACKEND는 smtp 또는 console 이어야 합니다")

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")

# DB 위치와 프론트엔드 주소(CORS)
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(BASE_DIR / 'routy.db').as_posix()}"

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://172.16.152.115:3000,http://localhost:3000"
    ).split(",")
    if origin.strip()
]

# 약관 버전: 약관 내용을 바꾸면 날짜를 올린다
TERMS_VERSION = "2026-10-06"
PRIVACY_VERSION = "2026-10-06"

# 비밀번호 암호화 강도와 로그인 토큰 유효 시간
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REMEMBER_ME_EXPIRE_DAYS = 30
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 15

# 이메일 인증 코드 규칙
VERIFICATION_CODE_EXPIRE_MINUTES = 10
VERIFIED_EMAIL_VALID_MINUTES = 30
MAX_VERIFICATION_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60

# 로그인·비밀번호 틀림 제한 (무차별 대입 방지)
MAX_LOGIN_FAILURES_PER_IP = 5
LOGIN_FAILURE_WINDOW_MINUTES = 15
MAX_ACCOUNT_LOGIN_FAILURES = 20
ACCOUNT_LOCK_MINUTES = 15

MAX_PASSWORD_CHECK_FAILURES = 5
PASSWORD_CHECK_WINDOW_MINUTES = 15

# API 요청 횟수 제한: (최대 횟수, 기간(초))
CHECK_USERNAME_RATE_LIMIT = (60, 10 * 60)
EMAIL_RATE_LIMIT = (5, 10 * 60)
EMAIL_DAILY_RATE_LIMIT = (30, 24 * 60 * 60)
VERIFY_RATE_LIMIT = (30, 10 * 60)
LOGIN_RATE_LIMIT = (30, 10 * 60)
