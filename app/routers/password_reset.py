# 비밀번호 재설정 API (로그인 전, 비밀번호를 잊었을 때)
# 흐름: 아이디+이메일로 코드 발송 → 코드 확인 후 재설정 토큰 발급 → 새 비밀번호 저장

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.config import VERIFICATION_CODE_EXPIRE_MINUTES
from app.database import get_db
from app.email_utils import build_email, send_email
from app.errors import AppError, ErrorCode
from app.models import User, VerificationPurpose
from app.queries import get_user_by_email, get_user_by_username
from app.rate_limit import EMAIL_SEND_LIMITS, VERIFY_LIMITS, clear_all_login_failures
from app.schemas import (
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetSendCodeRequest,
    PasswordResetVerifyResponse,
    VerifyCodeRequest,
)
from app.security import (
    create_password_reset_token,
    hash_password,
    read_password_reset_token,
    revoke_all_tokens,
)
from app.verification import check_code, find_verified, issue_code

router = APIRouter(prefix="/password-reset", tags=["password-reset"])


# 1단계: 인증 코드 발송
@router.post("/send-code", response_model=MessageResponse, dependencies=EMAIL_SEND_LIMITS)
def send_reset_code(
    body: PasswordResetSendCodeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = get_user_by_username(db, body.username.strip())
    if not user or user.email != body.email:
        raise AppError(ErrorCode.USER_NOT_FOUND, "아이디와 이메일이 일치하는 계정이 없습니다")

    code = issue_code(db, user.email, VerificationPurpose.PASSWORD_RESET)
    subject, text = build_email(
        "password_reset_code", body.lang.value, code=code, minutes=VERIFICATION_CODE_EXPIRE_MINUTES
    )
    background_tasks.add_task(send_email, user.email, subject, text)

    return {"message": "인증 코드가 이메일로 발송되었습니다"}


# 2단계: 코드 확인 → 15분짜리 재설정 토큰 발급
@router.post("/verify-code", response_model=PasswordResetVerifyResponse, dependencies=VERIFY_LIMITS)
def verify_reset_code(body: VerifyCodeRequest, db: Session = Depends(get_db)):
    check_code(db, body.email, VerificationPurpose.PASSWORD_RESET, body.code)

    user = get_user_by_email(db, body.email)
    if not user:
        raise AppError(ErrorCode.USER_NOT_FOUND)

    token, expires_in = create_password_reset_token(user)
    return {"reset_token": token, "expires_in": expires_in}


# 3단계: 새 비밀번호 저장 + 기존 로그인 전부 로그아웃 + 잠금 해제
@router.post("/confirm", response_model=MessageResponse, dependencies=VERIFY_LIMITS)
def confirm_reset(body: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    user_id = read_password_reset_token(body.reset_token)
    user = db.get(User, user_id)
    verification = (
        find_verified(db, user.email, VerificationPurpose.PASSWORD_RESET) if user else None
    )

    if not user or not verification:
        raise AppError(ErrorCode.INVALID_RESET_TOKEN)

    user.password_hash = hash_password(body.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    revoke_all_tokens(user)
    db.delete(verification)
    db.commit()
    clear_all_login_failures(user.username)

    return {"message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요"}
