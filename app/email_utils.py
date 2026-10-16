# 이메일 발송: 5개 언어(한국어·영어·일본어·간체·번체) 메일 문구와 Gmail 발송 기능.
# .env 에서 EMAIL_BACKEND=console 이면 실제로 보내지 않고 서버 창에 출력한다.

import logging
import smtplib
from email.message import EmailMessage

from app.config import EMAIL_BACKEND, GMAIL_ADDRESS, GMAIL_PASSWORD

logger = logging.getLogger("routy.email")

# 메일 문구 (용도별 × 언어별)
TEMPLATES = {
    "signup_code": {
        "ko": (
            "[Routy] 이메일 인증 코드",
            "인증 코드: {code}\n\n이 코드는 {minutes}분 후 만료됩니다.",
        ),
        "ja": (
            "[Routy] メール認証コード",
            "認証コード: {code}\n\nこのコードは{minutes}分後に無効になります。",
        ),
        "zh-CN": (
            "[Routy] 邮箱验证码",
            "验证码：{code}\n\n此验证码将在{minutes}分钟后失效。",
        ),
        "zh-TW": (
            "[Routy] 電子郵件驗證碼",
            "驗證碼：{code}\n\n此驗證碼將在{minutes}分鐘後失效。",
        ),
        "en": (
            "[Routy] Email verification code",
            "Your verification code: {code}\n\nThis code expires in {minutes} minutes.",
        ),
    },
    "password_reset_code": {
        "ko": (
            "[Routy] 비밀번호 재설정 인증 코드",
            "비밀번호 재설정 인증 코드: {code}\n\n이 코드는 {minutes}분 후 만료됩니다.\n"
            "본인이 요청하지 않았다면 이 메일을 무시해주세요.",
        ),
        "ja": (
            "[Routy] パスワード再設定の認証コード",
            "パスワード再設定の認証コード: {code}\n\nこのコードは{minutes}分後に無効になります。\n"
            "お心当たりがない場合は、このメールを無視してください。",
        ),
        "zh-CN": (
            "[Routy] 重置密码验证码",
            "重置密码验证码：{code}\n\n此验证码将在{minutes}分钟后失效。\n"
            "如果这不是您本人的操作，请忽略此邮件。",
        ),
        "zh-TW": (
            "[Routy] 重設密碼驗證碼",
            "重設密碼驗證碼：{code}\n\n此驗證碼將在{minutes}分鐘後失效。\n"
            "如果這不是您本人的操作，請忽略此郵件。",
        ),
        "en": (
            "[Routy] Password reset code",
            "Your password reset code: {code}\n\nThis code expires in {minutes} minutes.\n"
            "If you didn't request this, you can ignore this email.",
        ),
    },
    "find_username": {
        "ko": ("[Routy] 아이디 안내", "회원님의 아이디: {username}"),
        "ja": ("[Routy] IDのご案内", "お客様のID: {username}"),
        "zh-CN": ("[Routy] 账号ID通知", "您的账号ID：{username}"),
        "zh-TW": ("[Routy] 帳號ID通知", "您的帳號ID：{username}"),
        "en": ("[Routy] Your username", "Your username: {username}"),
    },
}


# 용도와 언어에 맞는 제목·본문 만들기 (없는 언어면 한국어)
def build_email(template: str, lang: str, **values) -> tuple[str, str]:
    variants = TEMPLATES[template]
    subject, body = variants.get(lang, variants["ko"])
    return subject, body.format(**values)


# 발송: 개발용(화면 출력) / 실제(Gmail SMTP)
def _print_email(recipient_email: str, subject: str, body: str) -> bool:
    line = "=" * 60
    print(f"\n{line}\n[개발용 메일 - 실제로 발송되지 않음]\n받는 사람: {recipient_email}\n제목: {subject}\n\n{body}\n{line}\n", flush=True)
    return True


def send_email(recipient_email: str, subject: str, body: str) -> bool:
    if EMAIL_BACKEND == "console":
        return _print_email(recipient_email, subject, body)

    if not GMAIL_ADDRESS or not GMAIL_PASSWORD:
        logger.error(".env에 GMAIL_ADDRESS 또는 GMAIL_PASSWORD가 없습니다")
        return False

    message = EmailMessage()
    message["From"] = GMAIL_ADDRESS
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, local_hostname="localhost", timeout=10) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.send_message(message)
        return True
    except Exception as error:
        logger.exception("이메일 발송 실패 (%s): %s", recipient_email, error)
        return False
