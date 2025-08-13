from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import os
import secrets
import hashlib
from src.config.database import get_db_connection
from src.utils.auth import get_password_hash
from src.utils.email import send_password_reset_email

router = APIRouter(tags=["auth"])


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


RESET_TOKEN_TTL_MINUTES = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))


@router.post("/auth/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email=%s AND is_active=TRUE", (req.email,))
                user = cursor.fetchone()
                # 존재하지 않는 이메일이어도 동일 응답 (정보 유출 방지)
                if not user:
                    return {"success": True}

                user_id = user["id"] if isinstance(user, dict) else user[0]

                # 토큰 생성 및 저장 (sha256 해시만 저장)
                raw_token = secrets.token_urlsafe(32)
                token_sha256 = hashlib.sha256(raw_token.encode()).hexdigest()
                expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

                cursor.execute(
                    """
                    INSERT INTO password_reset_tokens (user_id, token_sha256, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, token_sha256, expires_at),
                )
                # 비밀번호 재설정 링크 생성 및 메일 발송
                frontend_url = os.getenv("FRONTEND_URL", "https://www.realcatcha.com")
                reset_url = f"{frontend_url}/forgot-password?token={raw_token}"
                send_password_reset_email(req.email, reset_url)

                # 개발 편의: 토큰도 함께 반환
                return {"success": True, "reset_token": raw_token, "reset_url": reset_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"forgot-password 실패: {e}")


@router.post("/auth/reset-password")
def reset_password(req: ResetPasswordRequest):
    if not req.new_password or len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
    try:
        token_sha256 = hashlib.sha256(req.token.encode()).hexdigest()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, expires_at, used
                    FROM password_reset_tokens
                    WHERE token_sha256=%s
                    """,
                    (token_sha256,),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="유효하지 않은 토큰입니다.")

                token_id = row.get("id") if isinstance(row, dict) else row[0]
                user_id = row.get("user_id") if isinstance(row, dict) else row[1]
                expires_at = row.get("expires_at") if isinstance(row, dict) else row[2]
                used = row.get("used") if isinstance(row, dict) else row[3]

                if used:
                    raise HTTPException(status_code=400, detail="이미 사용된 토큰입니다.")
                if expires_at <= datetime.utcnow():
                    raise HTTPException(status_code=400, detail="만료된 토큰입니다.")

                # 사용자 비밀번호 업데이트
                new_hash = get_password_hash(req.new_password)
                cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, user_id))

                # 토큰 사용 처리
                cursor.execute("UPDATE password_reset_tokens SET used=TRUE WHERE id=%s", (token_id,))

                return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"reset-password 실패: {e}")

