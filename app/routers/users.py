# 내 정보 API (로그인 필요): 조회·수정, 동의 변경, 비밀번호 변경, 회원탈퇴

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.consents import ensure_sensitive_info_consent
from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models import EmailVerification, User
from app.rate_limit import (
    clear_all_login_failures,
    clear_password_check_failures,
    ensure_password_check_allowed,
    record_password_check_failure,
)
from app.schemas import (
    ChangePasswordRequest,
    ConsentUpdateRequest,
    DeleteAccountRequest,
    MessageResponse,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.security import (
    AuthContext,
    create_access_token,
    get_auth_context,
    get_current_user,
    hash_password,
    revoke_all_tokens,
    verify_password,
)

router = APIRouter(prefix="/users", tags=["users"])


# 현재 비밀번호 확인 (틀린 횟수 제한 포함) → 비밀번호 변경·탈퇴에서 사용
def _check_current_password(user: User, password: str, message: str | None = None) -> None:
    ensure_password_check_allowed(user.id)
    if not verify_password(password, user.password_hash):
        record_password_check_failure(user.id)
        raise AppError(ErrorCode.WRONG_CURRENT_PASSWORD, message)
    clear_password_check_failures(user.id)


# 내 정보 조회
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# 내 정보 수정 (보낸 항목만 바뀜)
@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True, mode="json")

    adds_sensitive_info = bool(updates.get("avoided_ingredients")) or updates.get("sensitivity") not in (None, "NONE")
    if adds_sensitive_info:
        ensure_sensitive_info_consent(current_user)

    for field, value in updates.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


# 동의 변경 (민감정보 동의를 철회하면 민감도·피하고 싶은 성분도 지움)
@router.put("/me/consents", response_model=UserResponse)
def update_consents(
    body: ConsentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    if body.sensitive_info is True and not current_user.sensitive_info_agreed:
        current_user.sensitive_info_agreed_at = now
    elif body.sensitive_info is False:
        current_user.sensitive_info_agreed_at = None
        current_user.avoided_ingredients = []
        current_user.sensitivity = "NONE"

    if body.marketing is True and not current_user.marketing_agreed:
        current_user.marketing_agreed_at = now
    elif body.marketing is False:
        current_user.marketing_agreed_at = None

    db.commit()
    db.refresh(current_user)
    return current_user


# 비밀번호 변경: 다른 기기 로그인은 끊고, 지금 기기에는 새 토큰 발급
@router.put("/me/password", response_model=TokenResponse)
def change_password(
    body: ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    user = auth.user
    _check_current_password(user, body.current_password)

    if verify_password(body.new_password, user.password_hash):
        raise AppError(ErrorCode.SAME_AS_CURRENT_PASSWORD)

    user.password_hash = hash_password(body.new_password)
    revoke_all_tokens(user)
    db.commit()

    token, expires_in = create_access_token(user, auth.remember_me)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


# 회원탈퇴: 비밀번호 확인 후 모든 정보 즉시 삭제
@router.delete("/me", response_model=MessageResponse)
def delete_me(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_current_password(current_user, body.password, "비밀번호가 올바르지 않습니다")

    user_id = current_user.id
    username = current_user.username
    db.execute(delete(EmailVerification).where(EmailVerification.email == current_user.email))
    db.delete(current_user)
    db.commit()
    clear_all_login_failures(username)
    clear_password_check_failures(user_id)

    return {"message": "회원 탈퇴가 완료되었습니다. 모든 정보가 삭제되었습니다"}
