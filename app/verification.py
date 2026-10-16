# 이메일 인증 코드 처리: 발급 → 확인 → '인증 완료' 기록 조회.
# 회원가입과 비밀번호 재설정이 함께 쓴다.

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import (
    MAX_VERIFICATION_ATTEMPTS,
    RESEND_COOLDOWN_SECONDS,
    VERIFICATION_CODE_EXPIRE_MINUTES,
    VERIFIED_EMAIL_VALID_MINUTES,
)
from app.errors import AppError, ErrorCode
from app.models import EmailVerification, VerificationPurpose
from app.security import as_utc, codes_match, generate_verification_code


def _find(db: Session, email: str, purpose: VerificationPurpose) -> EmailVerification | None:
    return db.scalar(
        select(EmailVerification).where(
            EmailVerification.email == email,
            EmailVerification.purpose == purpose.value,
        )
    )


# 만료된 인증 기록을 DB에서 정리
def purge_expired_verifications(db: Session) -> int:
    result = db.execute(
        delete(EmailVerification).where(EmailVerification.expires_at < datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount


# 새 코드 발급 (60초 안에 다시 요청하면 막음)
def issue_code(db: Session, email: str, purpose: VerificationPurpose) -> str:
    purge_expired_verifications(db)
    now = datetime.now(timezone.utc)
    verification = _find(db, email, purpose)

    if verification:
        elapsed = (now - as_utc(verification.sent_at)).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            retry_after = int(RESEND_COOLDOWN_SECONDS - elapsed) + 1
            raise AppError(
                ErrorCode.CODE_RESEND_TOO_SOON,
                f"{retry_after}초 후에 다시 요청해주세요",
                extra={"retry_after": retry_after},
            )
    else:
        verification = EmailVerification(email=email, purpose=purpose.value)
        db.add(verification)

    code = generate_verification_code()
    verification.code = code
    verification.is_verified = False
    verification.attempts = 0
    verification.expires_at = now + timedelta(minutes=VERIFICATION_CODE_EXPIRE_MINUTES)
    verification.sent_at = now

    db.commit()
    return code


# 코드 확인: 만료·불일치·시도 초과를 검사하고, 맞으면 '인증 완료'로 바꾼다
def check_code(db: Session, email: str, purpose: VerificationPurpose, code: str) -> EmailVerification:
    now = datetime.now(timezone.utc)
    verification = _find(db, email, purpose)

    if not verification:
        raise AppError(ErrorCode.VERIFICATION_NOT_FOUND)

    if now > as_utc(verification.expires_at):
        db.delete(verification)
        db.commit()
        raise AppError(ErrorCode.CODE_EXPIRED)

    if not codes_match(verification.code, code):
        verification.attempts += 1
        remaining = MAX_VERIFICATION_ATTEMPTS - verification.attempts

        if remaining <= 0:
            db.delete(verification)
            db.commit()
            raise AppError(ErrorCode.TOO_MANY_ATTEMPTS)

        db.commit()
        raise AppError(
            ErrorCode.CODE_MISMATCH,
            f"인증 코드가 일치하지 않습니다 (남은 시도 {remaining}회)",
            extra={"remaining_attempts": remaining},
        )

    if not verification.is_verified:
        verification.is_verified = True
        verification.expires_at = now + timedelta(minutes=VERIFIED_EMAIL_VALID_MINUTES)
        db.commit()
    return verification


# 인증을 마친(아직 유효한) 기록 찾기 → 가입·비밀번호 재설정 직전에 사용
def find_verified(db: Session, email: str, purpose: VerificationPurpose) -> EmailVerification | None:
    verification = _find(db, email, purpose)
    if not verification or not verification.is_verified:
        return None
    if datetime.now(timezone.utc) > as_utc(verification.expires_at):
        return None
    return verification
