import os
import smtplib
from email.message import EmailMessage


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_TLS = _bool_env("SMTP_USE_TLS", True)
SMTP_USE_SSL = _bool_env("SMTP_USE_SSL", False)
MAIL_SENDER_EMAIL = os.getenv("MAIL_SENDER_EMAIL", "no-reply@realcatcha.com")
MAIL_SENDER_NAME = os.getenv("MAIL_SENDER_NAME", "RealCatcha")


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """비밀번호 재설정 메일 발송. SMTP 설정이 없으면 개발 편의상 콘솔 로깅 후 True 반환."""
    subject = "[RealCatcha] 비밀번호 재설정 안내"
    body = (
        "안녕하세요,\n\n"
        "아래 링크를 클릭하여 비밀번호를 재설정해 주세요.\n"
        f"{reset_url}\n\n"
        "본 메일을 요청하지 않으셨다면 무시하셔도 됩니다.\n"
        "감사합니다.\n"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_SENDER_NAME} <{MAIL_SENDER_EMAIL}>"
    msg["To"] = to_email
    msg.set_content(body)

    # SMTP 미설정 시 콘솔 출력 후 성공 처리
    if not SMTP_HOST:
        print(f"[DEV] Send mail to {to_email}: {subject}\n{body}")
        return True

    try:
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"메일 발송 실패: {e}")
        return False


