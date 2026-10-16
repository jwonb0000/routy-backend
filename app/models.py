# DB 테이블 정의: 회원(users)과 이메일 인증 기록(email_verifications) 두 개.

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# 인증 코드의 용도 (회원가입 / 비밀번호 재설정)
class VerificationPurpose(str, Enum):
    SIGNUP = "signup"
    PASSWORD_RESET = "password_reset"


# 회원 테이블
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    # 계정 정보
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(10))
    age_group: Mapped[str] = mapped_column(String(10))
    # 피부 정보 (선택 입력): 피부 타입, 민감도(추천 순위 조정), 피하고 싶은 성분(추천에서 제외)
    skin_type: Mapped[str | None] = mapped_column(String(20))
    sensitivity: Mapped[str] = mapped_column(String(10), default="NONE")
    avoided_ingredients: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 보안: 토큰 무효화 버전, 로그인 실패 횟수와 잠금 시각
    is_email_verified: Mapped[bool] = mapped_column(default=False)
    token_version: Mapped[int] = mapped_column(default=0)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 약관·개인정보 동의 기록 (동의한 시각, 선택 동의는 안 했으면 비어 있음)
    terms_version: Mapped[str] = mapped_column(String(20))
    terms_agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    privacy_version: Mapped[str] = mapped_column(String(20))
    privacy_agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    age_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sensitive_info_agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    marketing_agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # 동의 여부 등을 True/False로 바로 꺼내 쓰기 위한 편의 속성
    @property
    def sensitive_info_agreed(self) -> bool:
        return self.sensitive_info_agreed_at is not None

    @property
    def marketing_agreed(self) -> bool:
        return self.marketing_agreed_at is not None

    @property
    def has_sensitive_info(self) -> bool:
        return bool(self.avoided_ingredients) or self.sensitivity != "NONE"


# 이메일 인증 코드 테이블 (이메일+용도 조합당 1건만 유지)
class EmailVerification(Base):
    __tablename__ = "email_verifications"
    __table_args__ = (UniqueConstraint("email", "purpose", name="uq_email_purpose"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(6))
    is_verified: Mapped[bool] = mapped_column(default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
