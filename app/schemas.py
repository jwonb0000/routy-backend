# 요청/응답 형식: 프론트가 보내는 값을 검사하고, 돌려줄 값의 모양을 정한다.
# 언어·나이대·피부타입 코드와 비밀번호 규칙은 프론트(routy-web)와 맞춰 둔 값이다.
# 국적은 받지 않고 사용자가 고른 언어만 저장한다.

import re
from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)


# 선택지 값
# Sensitivity: "새 화장품을 쓰면 따갑거나 붉어지나요?" → 거의 없음 / 가끔 / 자주
class Language(str, Enum):
    KO = "ko"
    JA = "ja"
    ZH_CN = "zh-CN"
    ZH_TW = "zh-TW"
    EN = "en"


class AgeGroup(str, Enum):
    TEENS = "teens"
    TWENTIES = "20s"
    THIRTIES = "30s"
    FORTIES = "40s"
    FIFTIES_PLUS = "50plus"


class Sensitivity(str, Enum):
    NONE = "NONE"
    SOMETIMES = "SOMETIMES"
    OFTEN = "OFTEN"


class SkinType(str, Enum):
    DRY = "DRY"
    OILY = "OILY"
    COMBINATION = "COMBINATION"
    NORMAL = "NORMAL"


# 입력값 검사 규칙: 아이디·비밀번호·피하고 싶은 성분
def _normalize_lower(value):
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _check_username_rule(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]{4,20}", value):
        raise ValueError("아이디는 영문과 숫자로 4~20자여야 합니다")
    return value


def _check_password_rule(value: str) -> str:
    if not re.fullmatch(r"[\x21-\x7E]+", value):
        raise ValueError("비밀번호는 영문, 숫자, 특수문자만 사용할 수 있습니다")
    if not (
        re.search(r"[A-Za-z]", value)
        and re.search(r"\d", value)
        and re.search(r"[!-/:-@\[-`{-~]", value)
    ):
        raise ValueError("비밀번호는 영문, 숫자, 특수문자를 각각 1자 이상 포함해야 합니다")
    return value


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


# 검사 규칙을 붙인 입력 타입들 (아래 요청 형식에서 재사용)
Email = Annotated[EmailStr, BeforeValidator(_normalize_lower)]
Username = Annotated[
    str,
    BeforeValidator(_normalize_lower),
    AfterValidator(_check_username_rule),
]
UsernameInput = Annotated[str, BeforeValidator(_normalize_lower), StringConstraints(max_length=64)]
PasswordInput = Annotated[str, StringConstraints(max_length=128)]
TokenInput = Annotated[str, StringConstraints(max_length=2048)]
NewPassword = Annotated[str, Field(min_length=8, max_length=64), AfterValidator(_check_password_rule)]
VerificationCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]
IngredientItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
AvoidedIngredients = Annotated[list[IngredientItem], Field(max_length=20), AfterValidator(_dedupe)]


# 공통 응답
class MessageResponse(BaseModel):
    message: str


# 회원가입: 아이디 중복확인 → 이메일 인증 → 가입
class CheckUsernameRequest(BaseModel):
    username: Username


class CheckUsernameResponse(BaseModel):
    available: bool
    message: str


class SendCodeRequest(BaseModel):
    email: Email
    lang: Language = Language.KO


class VerifyCodeRequest(BaseModel):
    email: Email
    code: VerificationCode


class VerifyEmailResponse(BaseModel):
    verified: bool
    message: str


class SignupAgreements(BaseModel):
    terms: bool = False
    privacy: bool = False
    age_over_14: bool = False
    sensitive_info: bool = False
    marketing: bool = False


class SignupRequest(BaseModel):
    username: Username
    email: Email
    password: NewPassword
    language: Language
    age_group: AgeGroup
    skin_type: SkinType | None = None
    sensitivity: Sensitivity = Sensitivity.NONE
    avoided_ingredients: AvoidedIngredients = []
    agreements: SignupAgreements


# 내 정보: 조회·동의 변경·탈퇴·수정
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    language: str
    age_group: str
    skin_type: str | None = None
    sensitivity: str
    avoided_ingredients: list[str]
    is_email_verified: bool
    terms_version: str
    privacy_version: str
    sensitive_info_agreed: bool
    marketing_agreed: bool


class ConsentUpdateRequest(BaseModel):
    sensitive_info: bool | None = None
    marketing: bool | None = None


class DeleteAccountRequest(BaseModel):
    password: PasswordInput


class UserUpdateRequest(BaseModel):
    language: Language | None = None
    age_group: AgeGroup | None = None
    skin_type: SkinType | None = None
    sensitivity: Sensitivity | None = None
    avoided_ingredients: AvoidedIngredients | None = None

    @model_validator(mode="after")
    def required_fields_not_null(self):
        for name in ("language", "age_group", "sensitivity", "avoided_ingredients"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}은(는) 비울 수 없습니다")
        return self


# 로그인·아이디 찾기·비밀번호 재설정·비밀번호 변경
class LoginRequest(BaseModel):
    username: UsernameInput
    password: PasswordInput
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class FindUsernameRequest(BaseModel):
    email: Email
    lang: Language = Language.KO


class PasswordResetSendCodeRequest(BaseModel):
    username: UsernameInput
    email: Email
    lang: Language = Language.KO


class PasswordResetVerifyResponse(BaseModel):
    reset_token: TokenInput
    expires_in: int


class PasswordResetConfirmRequest(BaseModel):
    reset_token: TokenInput
    new_password: NewPassword


class ChangePasswordRequest(BaseModel):
    current_password: PasswordInput
    new_password: NewPassword
