# 회원가입·로그인 API
# 가입 흐름: 아이디 중복확인 → 이메일 코드 발송 → 코드 확인 → 가입

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import (
    ACCOUNT_LOCK_MINUTES,
    MAX_ACCOUNT_LOGIN_FAILURES,
    VERIFICATION_CODE_EXPIRE_MINUTES,
)
from app.consents import ensure_signup_agreements, signup_consent_fields
from app.database import get_db
from app.email_utils import build_email, send_email
from app.errors import AppError, ErrorCode
from app.models import User, VerificationPurpose
from app.queries import get_user_by_email, get_user_by_username
from app.rate_limit import (
    CHECK_USERNAME_LIMITS,
    EMAIL_SEND_LIMITS,
    LOGIN_LIMITS,
    VERIFY_LIMITS,
    clear_login_failures,
    ensure_login_not_blocked,
    record_login_failure,
)
from app.schemas import (
    CheckUsernameRequest,
    CheckUsernameResponse,
    FindUsernameRequest,
    LoginRequest,
    MessageResponse,
    SendCodeRequest,
    Sensitivity,
    SignupRequest,
    TokenResponse,
    UserResponse,
    VerifyCodeRequest,
    VerifyEmailResponse,
)
from app.security import as_utc, create_access_token, hash_password, verify_password
from app.verification import check_code, find_verified, issue_code

router = APIRouter(tags=["auth"])


# 아이디 중복 확인
@router.post(
    "/check-username",
    response_model=CheckUsernameResponse,
    dependencies=CHECK_USERNAME_LIMITS,
)
def check_username(body: CheckUsernameRequest, db: Session = Depends(get_db)):
    if get_user_by_username(db, body.username):
        return {"available": False, "message": "이미 사용 중인 아이디입니다"}
    return {"available": True, "message": "사용 가능한 아이디입니다"}


# 가입용 이메일 인증 코드 발송 (메일은 응답 후 백그라운드로 보냄)
@router.post(
    "/send-verification-email",
    response_model=MessageResponse,
    dependencies=EMAIL_SEND_LIMITS,
)
def send_verification_email(
    body: SendCodeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if get_user_by_email(db, body.email):
        raise AppError(ErrorCode.EMAIL_TAKEN)

    code = issue_code(db, body.email, VerificationPurpose.SIGNUP)
    subject, text = build_email(
        "signup_code", body.lang.value, code=code, minutes=VERIFICATION_CODE_EXPIRE_MINUTES
    )
    background_tasks.add_task(send_email, body.email, subject, text)

    return {"message": "인증 코드가 이메일로 발송되었습니다"}


# 인증 코드 확인
@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    dependencies=VERIFY_LIMITS,
)
def verify_email(body: VerifyCodeRequest, db: Session = Depends(get_db)):
    check_code(db, body.email, VerificationPurpose.SIGNUP, body.code)
    return {"verified": True, "message": "이메일 인증이 완료되었습니다"}


# 회원가입: 이메일 인증·중복·동의를 확인한 뒤 저장
@router.post("/signup", response_model=UserResponse)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    verification = find_verified(db, body.email, VerificationPurpose.SIGNUP)
    if not verification:
        raise AppError(ErrorCode.EMAIL_NOT_VERIFIED)

    if get_user_by_username(db, body.username):
        raise AppError(ErrorCode.USERNAME_TAKEN)

    if get_user_by_email(db, body.email):
        raise AppError(ErrorCode.EMAIL_TAKEN)

    has_sensitive_info = bool(body.avoided_ingredients) or body.sensitivity != Sensitivity.NONE
    ensure_signup_agreements(body.agreements, has_sensitive_info)

    new_user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        language=body.language.value,
        age_group=body.age_group.value,
        skin_type=body.skin_type.value if body.skin_type else None,
        sensitivity=body.sensitivity.value,
        avoided_ingredients=body.avoided_ingredients,
        is_email_verified=True,
        **signup_consent_fields(body.agreements, datetime.now(timezone.utc)),
    )
    db.add(new_user)
    db.delete(verification)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(ErrorCode.USERNAME_OR_EMAIL_TAKEN)

    db.refresh(new_user)
    return new_user


# 로그인
# 잠금 2단계: 아이디+IP로 5번 틀리면 잠시 차단, 계정 전체로 20번 틀리면 15분 잠금
@router.post("/login", response_model=TokenResponse, dependencies=LOGIN_LIMITS)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    username = body.username.strip()
    ensure_login_not_blocked(request, username)

    user = get_user_by_username(db, username)
    if not user:
        record_login_failure(request, username)
        raise AppError(ErrorCode.INVALID_CREDENTIALS)

    now = datetime.now(timezone.utc)
    if user.locked_until and as_utc(user.locked_until) > now:
        retry_after = math.ceil((as_utc(user.locked_until) - now).total_seconds())
        raise AppError(ErrorCode.ACCOUNT_LOCKED, extra={"retry_after": retry_after})

    if not verify_password(body.password, user.password_hash):
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= MAX_ACCOUNT_LOGIN_FAILURES:
            user.failed_login_attempts = 0
            user.locked_until = now + timedelta(minutes=ACCOUNT_LOCK_MINUTES)
            db.commit()
            raise AppError(ErrorCode.ACCOUNT_LOCKED, extra={"retry_after": ACCOUNT_LOCK_MINUTES * 60})

        db.commit()
        record_login_failure(request, username)
        raise AppError(ErrorCode.INVALID_CREDENTIALS)

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    clear_login_failures(request, username)

    token, expires_in = create_access_token(user, body.remember_me)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


# 아이디 찾기: 가입한 이메일로 아이디를 보내준다
@router.post(
    "/find-username",
    response_model=MessageResponse,
    dependencies=EMAIL_SEND_LIMITS,
)
def find_username(
    body: FindUsernameRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, body.email)
    if not user:
        raise AppError(ErrorCode.USER_NOT_FOUND, "해당 이메일로 가입된 계정을 찾을 수 없습니다")

    subject, text = build_email("find_username", body.lang.value, username=user.username)
    background_tasks.add_task(send_email, body.email, subject, text)

    return {"message": "아이디가 이메일로 발송되었습니다"}
