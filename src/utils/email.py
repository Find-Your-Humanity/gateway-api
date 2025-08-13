import os
import smtplib
from email.message import EmailMessage
from typing import Optional


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


def send_password_reset_email(to_email: str, reset_url: Optional[str] = None, code: Optional[str] = None) -> bool:
    """비밀번호 재설정 메일 발송.

    - reset_url: 링크 기반 재설정
    - code: 6자리 인증코드 기반 재설정
    둘 다 제공되면 링크와 코드를 함께 안내합니다.
    SMTP 설정이 없으면 개발 편의상 콘솔 로깅 후 True 반환.
    """
    subject = "[RealCatcha] 비밀번호 재설정 안내"

    text_lines = ["안녕하세요,", "",]
    if code:
        text_lines.append(f"인증코드: {code}")
    if reset_url:
        text_lines.append("아래 링크를 클릭하여 비밀번호를 재설정해 주세요.")
        text_lines.append(reset_url)
    text_lines.extend(["", "본 메일을 요청하지 않으셨다면 무시하셔도 됩니다.", "감사합니다."])
    body = "\n".join(text_lines)

    # 심플한 HTML 템플릿
    html = f"""
    <div style="font-family:Inter, Pretendard, Arial; line-height:1.6; color:#111">
      <p>안녕하세요,</p>
      {f'<p style="margin:16px 0">아래 인증코드를 입력해 비밀번호를 재설정해 주세요.</p><div style="font-size:28px;font-weight:700;letter-spacing:2px;background:#f5f7ff;border:1px solid #dfe4ff;border-radius:8px;padding:16px 24px;display:inline-block">{code}</div>' if code else ''}
      {f'<p style="margin:16px 0">또는 아래 링크를 클릭하여 재설정할 수 있습니다.</p><p><a href="{reset_url}" style="color:#5b6cff;text-decoration:none">{reset_url}</a></p>' if reset_url else ''}
      <p style="margin-top:24px;color:#555">본 메일을 요청하지 않으셨다면 무시하셔도 됩니다.</p>
      <p style="color:#555">감사합니다.<br/>{MAIL_SENDER_NAME}</p>
    </div>
    """

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_SENDER_NAME} <{MAIL_SENDER_EMAIL}>"
    msg["To"] = to_email
    msg.set_content(body)
    msg.add_alternative(html, subtype="html")

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



