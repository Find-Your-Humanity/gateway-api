from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timedelta
import os
import secrets
import hashlib
from src.config.database import get_db_connection
from src.utils.auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    create_user,
)
from src.utils.email import send_password_reset_email, send_email_verification_code

router = APIRouter(prefix="/api", tags=["auth"])


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class RequestResetCode(BaseModel):
    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
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
                # 비밀번호 재설정 링크 생성 및 메일 발송 (HTML 템플릿 사용)
                frontend_url = os.getenv("FRONTEND_URL", "https://www.realcatcha.com")
                reset_url = f"{frontend_url}/reset-password?token={raw_token}"
                send_password_reset_email(req.email, reset_url=reset_url)

                # 개발 편의: 토큰도 함께 반환
                return {"success": True, "reset_token": raw_token, "reset_url": reset_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"forgot-password 실패: {e}")


@router.post("/auth/reset-password")
def reset_password(req: ResetPasswordRequest):
    import re
    strong = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
    if not req.new_password or not strong.match(req.new_password):
        raise HTTPException(status_code=400, detail="비밀번호는 영문, 숫자, 특수문자 조합 8자 이상이어야 합니다.")
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

                # 사용자 비밀번호 업데이트 + 이메일 소유 증명으로 is_verified 부여
                new_hash = get_password_hash(req.new_password)
                cursor.execute("UPDATE users SET password_hash=%s, is_verified=TRUE WHERE id=%s", (new_hash, user_id))

                # 토큰 사용 처리
                cursor.execute("UPDATE password_reset_tokens SET used=TRUE WHERE id=%s", (token_id,))

                return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"reset-password 실패: {e}")


# ===== 6자리 인증코드(OTP) 기반 재설정 =====

@router.post("/auth/forgot-password/code")
def request_reset_code(req: RequestResetCode):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email=%s AND is_active=TRUE", (req.email,))
                user = cursor.fetchone()
                if not user:
                    return {"success": True}

                user_id = user["id"] if isinstance(user, dict) else user[0]

                # 6자리 코드 생성(선두 0 허용)
                code = f"{secrets.randbelow(1000000):06d}"
                code_sha256 = hashlib.sha256(code.encode()).hexdigest()
                expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

                # 기존 미사용 코드 무효화(선택)
                cursor.execute(
                    "UPDATE password_reset_codes SET used=TRUE WHERE user_id=%s AND used=FALSE",
                    (user_id,),
                )

                cursor.execute(
                    """
                    INSERT INTO password_reset_codes (user_id, code_sha256, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, code_sha256, expires_at),
                )

                # 메일 발송: 코드/링크 형식 모두 지원되는 템플릿
                frontend_url = os.getenv("FRONTEND_URL", "https://www.realcatcha.com")
                reset_url = f"{frontend_url}/forgot-password"
                send_password_reset_email(req.email, reset_url=reset_url, code=code)

                return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"request-reset-code 실패: {e}")


@router.post("/auth/reset-password/code")
def verify_reset_code(req: VerifyResetCodeRequest):
    import re
    strong = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
    if not req.new_password or not strong.match(req.new_password):
        raise HTTPException(status_code=400, detail="비밀번호는 영문, 숫자, 특수문자 조합 8자 이상이어야 합니다.")
    try:
        code_sha256 = hashlib.sha256(req.code.encode()).hexdigest()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, expires_at, used
                    FROM password_reset_codes
                    WHERE code_sha256=%s
                    """,
                    (code_sha256,),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="유효하지 않은 인증코드입니다.")

                token_id = row.get("id") if isinstance(row, dict) else row[0]
                user_id = row.get("user_id") if isinstance(row, dict) else row[1]
                expires_at = row.get("expires_at") if isinstance(row, dict) else row[2]
                used = row.get("used") if isinstance(row, dict) else row[3]

                if used:
                    raise HTTPException(status_code=400, detail="이미 사용된 인증코드입니다.")
                if expires_at <= datetime.utcnow():
                    raise HTTPException(status_code=400, detail="만료된 인증코드입니다.")

                # 이메일 확인(코드 탈취 방지용, 동일 사용자 매칭)
                cursor.execute("SELECT id FROM users WHERE id=%s AND email=%s", (user_id, req.email))
                user_row = cursor.fetchone()
                if not user_row:
                    raise HTTPException(status_code=400, detail="인증코드와 이메일이 일치하지 않습니다.")

                # 비밀번호 변경 + 이메일 소유 증명으로 is_verified 부여
                new_hash = get_password_hash(req.new_password)
                cursor.execute("UPDATE users SET password_hash=%s, is_verified=TRUE WHERE id=%s", (new_hash, user_id))

                # 코드 사용 처리
                cursor.execute("UPDATE password_reset_codes SET used=TRUE WHERE id=%s", (token_id,))

                return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"verify-reset-code 실패: {e}")


# ===== 로그인/회원가입 =====

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


@router.post("/auth/login")
def login(req: LoginRequest):
    try:
        user = authenticate_user(req.email, req.password)
        if not user:
            raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

        access_token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"login 실패: {e}")


class SignupRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3)
    password: str
    full_name: Optional[str] = None
    contact: Optional[str] = None


@router.post("/auth/signup")
def signup(req: SignupRequest):
    try:
        # 비밀번호 강도 검사 (영문/숫자/특수문자 조합 8자 이상)
        import re
        strong = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
        if not strong.match(req.password):
            raise HTTPException(status_code=422, detail=[{"field":"password","message":"비밀번호는 영문, 숫자, 특수문자 조합 8자 이상이어야 합니다."}])

        # 사전 조건: 이메일 인증 완료 여부 확인
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM email_verification_codes
                    WHERE email=%s AND used=TRUE AND expires_at > NOW()
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (req.email,),
                )
                verified_row = cursor.fetchone()
                if not verified_row:
                    raise HTTPException(status_code=400, detail="이메일 인증이 필요합니다.")

        user, err = create_user(
            email=req.email,
            username=req.username,
            password=req.password,
            full_name=req.full_name,
            contact=req.contact,
        )
        if err:
            if err == "email_exists":
                raise HTTPException(status_code=409, detail="이미 존재하는 이메일입니다.")
            if err == "username_exists":
                raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다.")
            if err == "contact_exists":
                raise HTTPException(status_code=409, detail="이미 존재하는 연락처입니다.")
            raise HTTPException(status_code=400, detail="회원가입에 실패했습니다.")

        # 사전 인증을 통과했으므로 사용자 레코드도 즉시 is_verified=TRUE 로 마크
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET is_verified=TRUE WHERE id=%s", (user['id'],))
        except Exception:
            # 비치명적: 업데이트 실패 시에도 가입은 완료
            pass

        return {"success": True, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"signup 실패: {e}")


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


@router.post("/auth/verify-email")
def verify_email(req: VerifyEmailRequest):
    try:
        import hashlib
        code_sha256 = hashlib.sha256(req.code.encode()).hexdigest()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, expires_at, used FROM email_verification_codes
                    WHERE email=%s AND code_sha256=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (req.email, code_sha256),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="유효하지 않은 인증코드입니다.")
                from datetime import datetime
                expires_at = row.get("expires_at") if isinstance(row, dict) else row[1]
                used = row.get("used") if isinstance(row, dict) else row[2]
                if used:
                    raise HTTPException(status_code=400, detail="이미 사용된 인증코드입니다.")
                if expires_at <= datetime.utcnow():
                    raise HTTPException(status_code=400, detail="만료된 인증코드입니다.")

                # 이메일 인증 완료 처리: users.is_verified=TRUE로 업데이트
                token_id = row.get("id") if isinstance(row, dict) else row[0]
                cursor.execute("UPDATE email_verification_codes SET used=TRUE WHERE id=%s", (token_id,))
                cursor.execute("UPDATE users SET is_verified=TRUE WHERE email=%s", (req.email,))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"verify-email 실패: {e}")


class RequestEmailVerification(BaseModel):
    email: EmailStr


@router.post("/auth/verify-email/request")
def request_email_verification(req: RequestEmailVerification):
    try:
        import secrets, hashlib
        from datetime import datetime, timedelta
        # 이미 가입된 이메일인지 확인
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email=%s", (req.email,))
                exists = cursor.fetchone()
                if exists:
                    raise HTTPException(status_code=409, detail="이미 존재하는 사용자입니다.")

                # 코드 생성/저장
                code = f"{secrets.randbelow(1000000):06d}"
                code_sha256 = hashlib.sha256(code.encode()).hexdigest()
                expires_at = datetime.utcnow() + timedelta(minutes=int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30")))
                cursor.execute(
                    """
                    INSERT INTO email_verification_codes (email, code_sha256, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (req.email, code_sha256, expires_at),
                )

        # 메일 발송
        send_email_verification_code(req.email, code)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"request-email-verification 실패: {e}")
