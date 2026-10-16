# 에러 처리: 모든 에러를 {code, message} 형식으로 프론트에 돌려준다.

from enum import Enum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# 에러 코드 목록 (프론트는 이 code 값을 보고 화면 처리를 나눈다)
class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    HTTP_ERROR = "HTTP_ERROR"
    USERNAME_TAKEN = "USERNAME_TAKEN"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    USERNAME_OR_EMAIL_TAKEN = "USERNAME_OR_EMAIL_TAKEN"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    CODE_RESEND_TOO_SOON = "CODE_RESEND_TOO_SOON"
    VERIFICATION_NOT_FOUND = "VERIFICATION_NOT_FOUND"
    CODE_EXPIRED = "CODE_EXPIRED"
    CODE_MISMATCH = "CODE_MISMATCH"
    TOO_MANY_ATTEMPTS = "TOO_MANY_ATTEMPTS"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOO_MANY_LOGIN_ATTEMPTS = "TOO_MANY_LOGIN_ATTEMPTS"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    INVALID_RESET_TOKEN = "INVALID_RESET_TOKEN"
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_TOKEN = "INVALID_TOKEN"
    WRONG_CURRENT_PASSWORD = "WRONG_CURRENT_PASSWORD"
    TOO_MANY_PASSWORD_ATTEMPTS = "TOO_MANY_PASSWORD_ATTEMPTS"
    SAME_AS_CURRENT_PASSWORD = "SAME_AS_CURRENT_PASSWORD"


# 에러 코드별 HTTP 상태 번호와 기본 안내 문구
ERRORS: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.VALIDATION_ERROR: (422, "입력값을 확인해주세요"),
    ErrorCode.NOT_FOUND: (404, "요청한 주소를 찾을 수 없습니다"),
    ErrorCode.METHOD_NOT_ALLOWED: (405, "허용되지 않는 요청 방식입니다"),
    ErrorCode.HTTP_ERROR: (400, "요청을 처리할 수 없습니다"),
    ErrorCode.USERNAME_TAKEN: (400, "이미 사용 중인 아이디입니다"),
    ErrorCode.EMAIL_TAKEN: (400, "이미 가입된 이메일입니다"),
    ErrorCode.USERNAME_OR_EMAIL_TAKEN: (400, "이미 사용 중인 아이디 또는 이메일입니다"),
    ErrorCode.EMAIL_NOT_VERIFIED: (400, "먼저 이메일 인증을 완료해주세요"),
    ErrorCode.CONSENT_REQUIRED: (400, "필수 항목에 동의해주세요"),
    ErrorCode.CODE_RESEND_TOO_SOON: (429, "잠시 후 다시 요청해주세요"),
    ErrorCode.VERIFICATION_NOT_FOUND: (404, "인증 요청 내역이 없습니다. 인증 코드를 먼저 요청해주세요"),
    ErrorCode.CODE_EXPIRED: (400, "인증 코드가 만료되었습니다. 다시 요청해주세요"),
    ErrorCode.CODE_MISMATCH: (400, "인증 코드가 일치하지 않습니다"),
    ErrorCode.TOO_MANY_ATTEMPTS: (429, "시도 횟수를 초과했습니다. 인증 코드를 다시 요청해주세요"),
    ErrorCode.RATE_LIMITED: (429, "요청이 너무 많습니다. 잠시 후 다시 시도해주세요"),
    ErrorCode.INVALID_CREDENTIALS: (401, "아이디 또는 비밀번호가 올바르지 않습니다"),
    ErrorCode.TOO_MANY_LOGIN_ATTEMPTS: (429, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요"),
    ErrorCode.ACCOUNT_LOCKED: (
        429,
        "여러 곳에서 로그인 실패가 반복되어 계정이 잠시 잠겼습니다. 비밀번호 찾기로 바로 풀 수 있습니다",
    ),
    ErrorCode.USER_NOT_FOUND: (404, "일치하는 계정을 찾을 수 없습니다"),
    ErrorCode.INVALID_RESET_TOKEN: (400, "비밀번호 재설정 시간이 만료되었습니다. 처음부터 다시 진행해주세요"),
    ErrorCode.UNAUTHORIZED: (401, "로그인이 필요합니다"),
    ErrorCode.INVALID_TOKEN: (401, "로그인이 만료되었습니다. 다시 로그인해주세요"),
    ErrorCode.WRONG_CURRENT_PASSWORD: (400, "현재 비밀번호가 올바르지 않습니다"),
    ErrorCode.TOO_MANY_PASSWORD_ATTEMPTS: (429, "비밀번호를 너무 많이 틀렸습니다. 잠시 후 다시 시도해주세요"),
    ErrorCode.SAME_AS_CURRENT_PASSWORD: (400, "현재 비밀번호와 다른 비밀번호를 입력해주세요"),
}


# 코드 어디서든 raise AppError(ErrorCode.XXX) 로 에러를 내면 된다
class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str | None = None, extra: dict | None = None):
        status_code, default_message = ERRORS[code]
        self.code = code
        self.status_code = status_code
        self.message = message or default_message
        self.extra = extra or {}
        super().__init__(self.message)


# 없는 주소(404), 잘못된 요청 방식(405)도 같은 형식으로 바꿔 준다
HTTP_STATUS_CODES = {
    404: (ErrorCode.NOT_FOUND, "요청한 주소를 찾을 수 없습니다"),
    405: (ErrorCode.METHOD_NOT_ALLOWED, "허용되지 않는 요청 방식입니다"),
}


def _json_error(status_code: int, content: dict, headers: dict | None = None) -> JSONResponse:
    merged = dict(headers or {})
    if status_code == 401:
        merged["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=status_code, content=content, headers=merged or None)


# 위 에러들을 FastAPI에 등록
# 입력값 오류(422)는 어떤 칸이 왜 틀렸는지 errors 목록으로 알려준다
def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return _json_error(
            exc.status_code,
            {"code": exc.code.value, "message": exc.message, **exc.extra},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code, message = HTTP_STATUS_CODES.get(
            exc.status_code, (ErrorCode.HTTP_ERROR, str(exc.detail))
        )
        return _json_error(
            exc.status_code,
            {"code": code.value, "message": message},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        status_code, message = ERRORS[ErrorCode.VALIDATION_ERROR]
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]),
                "reason": error["msg"],
            }
            for error in exc.errors()
        ]
        return _json_error(
            status_code,
            {"code": ErrorCode.VALIDATION_ERROR.value, "message": message, "errors": errors},
        )
