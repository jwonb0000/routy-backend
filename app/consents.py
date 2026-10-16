# 약관·개인정보 동의 처리: 필수 동의 확인과 동의 시각 기록.

from datetime import datetime

from app.config import PRIVACY_VERSION, TERMS_VERSION
from app.errors import AppError, ErrorCode
from app.models import User
from app.schemas import SignupAgreements

REQUIRED_AGREEMENTS = ("terms", "privacy", "age_over_14")


# 가입 시 필수 동의(약관·개인정보·만 14세) 확인. 민감도·피하고 싶은 성분을 넣으면 민감정보 동의도 필수
def ensure_signup_agreements(agreements: SignupAgreements, has_sensitive_info: bool) -> None:
    missing = [name for name in REQUIRED_AGREEMENTS if not getattr(agreements, name)]
    if has_sensitive_info and not agreements.sensitive_info:
        missing.append("sensitive_info")
    if missing:
        raise AppError(ErrorCode.CONSENT_REQUIRED, extra={"missing": missing})


# 동의 내용을 DB에 저장할 값으로 바꾸기 (동의 시각, 약관 버전)
def signup_consent_fields(agreements: SignupAgreements, now: datetime) -> dict:
    return {
        "terms_version": TERMS_VERSION,
        "terms_agreed_at": now,
        "privacy_version": PRIVACY_VERSION,
        "privacy_agreed_at": now,
        "age_confirmed_at": now,
        "sensitive_info_agreed_at": now if agreements.sensitive_info else None,
        "marketing_agreed_at": now if agreements.marketing else None,
    }


# 가입 후 민감도·피하고 싶은 성분을 추가할 때 민감정보 동의 여부 확인
def ensure_sensitive_info_consent(user: User) -> None:
    if not user.sensitive_info_agreed:
        raise AppError(
            ErrorCode.CONSENT_REQUIRED,
            "피부 민감도·피하고 싶은 성분을 저장하려면 민감정보 수집에 동의해주세요",
            extra={"missing": ["sensitive_info"]},
        )
