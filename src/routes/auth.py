from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
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
    verify_token,
    get_user_by_id,
    create_refresh_token_for_user,
    verify_and_rotate_refresh_token,
)
from src.utils.email import send_password_reset_email, send_email_verification_code
from src.config.oauth import get_google_auth_url
from src.utils.google_oauth import exchange_code_for_token, get_google_user_info, create_or_update_user_from_google
import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["auth"])
class RefreshResponse(BaseModel):
    success: bool
    access_token: str

@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh_token(request: Request, response: Response):
    """리프레시 쿠키로 액세스 토큰 재발급 (롤링 전략)."""
    try:
        raw = request.cookies.get("captcha_refresh")
        if not raw:
            logger.error("리프레시 토큰이 없습니다")
            raise HTTPException(status_code=401, detail="리프레시 토큰이 없습니다.")

        logger.info(f"리프레시 토큰 갱신 시도: {raw[:10]}...")
        
        result = verify_and_rotate_refresh_token(raw_token=raw, rotate=True)
        if not result:
            logger.error("리프레시 토큰이 유효하지 않습니다")
            raise HTTPException(status_code=401, detail="리프레시 토큰이 유효하지 않습니다.")

        user_id = result["user_id"]
        logger.info(f"리프레시 토큰 검증 성공: 사용자 {user_id}")
        
        # 새 액세스 토큰 발급
        from datetime import timedelta
        access = create_access_token({"sub": str(user_id)}, expires_delta=timedelta(minutes=30))

        # 쿠키 갱신
        response.set_cookie(
            key="captcha_token",
            value=access,
            domain=".realcatcha.com",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=60 * 30
        )

        # 롤링된 새 리프레시가 있으면 교체
        new_raw = result.get("new_refresh_raw")
        if new_raw:
            response.set_cookie(
                key="captcha_refresh",
                value=new_raw,
                domain=".realcatcha.com",
                httponly=True,
                secure=True,
                samesite="none",
                max_age=60 * 60 * 24 * 14
            )
            logger.info("새 리프레시 토큰으로 교체됨")

        logger.info(f"토큰 갱신 완료: 사용자 {user_id}")
        return {"success": True, "access_token": access}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"토큰 갱신 실패: {e}")
        raise HTTPException(status_code=500, detail=f"refresh 실패: {e}")



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
def login(req: LoginRequest, response: Response):
    try:
        user = authenticate_user(req.email, req.password)
        if not user:
            raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

        access_token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
        # Create refresh token
        refresh_raw, _, refresh_exp = create_refresh_token_for_user(user_id=int(user["id"]))
        
        # 쿠키로 토큰 설정 (부모 도메인 .realcatcha.com)
        response.set_cookie(
            key="captcha_token",
            value=access_token,
            domain=".realcatcha.com",  # 모든 서브도메인에서 접근 가능
            httponly=True,  # XSS 방지
            secure=True,    # HTTPS에서만 전송
            samesite="none", # CSRF 방지하면서 일반적인 사이트 간 이동 허용
            max_age=60 * 60 * 24 * 7  # 7일 (초 단위)
        )

        # Set refresh cookie (longer lived). Optional: Path lock to /api/auth/refresh
        response.set_cookie(
            key="captcha_refresh",
            value=refresh_raw,
            domain=".realcatcha.com",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=60 * 60 * 24 * 14
        )
        
        return {
            "success": True,
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


@router.post("/auth/logout")
def logout(response: Response):
    """로그아웃 - 쿠키 제거"""
    try:
        # 쿠키 제거 (같은 도메인/경로로 빈 값과 과거 만료일 설정)
        response.set_cookie(
            key="captcha_token",
            value="",
            domain=".realcatcha.com",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=0  # 즉시 만료
        )
        response.set_cookie(
            key="captcha_refresh",
            value="",
            domain=".realcatcha.com",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=0
        )
        return {"success": True, "message": "로그아웃되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"logout 실패: {e}")


def get_current_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Request에서 사용자 정보 추출 (Authorization 헤더 또는 쿠키에서)"""
    try:
        # 1. Authorization 헤더에서 토큰 확인
        auth_header = request.headers.get("authorization")
        token = None
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            # 2. 쿠키에서 토큰 확인
            token = request.cookies.get("captcha_token")
        
        if not token:
            return None
            
        # 토큰 검증
        payload = verify_token(token)
        if not payload:
            return None
            
        user_id = payload.get("sub")
        if not user_id:
            return None
            
        # 사용자 정보 조회
        user = get_user_by_id(int(user_id))
        return user
        
    except Exception as e:
        print(f"❌ 사용자 인증 오류: {e}")
        return None


@router.get("/auth/me")
def get_current_user(request: Request, response: Response):
    """현재 로그인된 사용자 정보 반환 (쿠키 또는 헤더 토큰 기반)"""
    try:
        user = get_current_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")
        
        # 백필: refresh 쿠키가 없으면 1회 자동 발급
        try:
            has_refresh = bool(request.cookies.get("captcha_refresh"))
            if not has_refresh:
                # 최소 정보만 기록 (User-Agent 기반 디바이스 정보)
                ua = request.headers.get("user-agent")
                _raw, _, _exp = create_refresh_token_for_user(user_id=int(user["id"]), device_info=ua)
                response.set_cookie(
                    key="captcha_refresh",
                    value=_raw,
                    domain=".realcatcha.com",
                    httponly=True,
                    secure=True,
                    samesite="none",
                    max_age=60 * 60 * 24 * 14
                )
        except Exception:
            # 백필 실패는 비치명적
            pass

        return {
            "success": True,
            "user": user
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 정보 조회 실패: {e}")


# ==================== 인증 헬퍼 함수 ====================
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 인증 실패: {e}")


# ==================== Google OAuth 라우트 ====================

@router.get("/auth/google")
def google_login():
    """Google OAuth 로그인 URL 생성"""
    try:
        auth_url = get_google_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google OAuth URL 생성 실패: {e}")


@router.get("/auth/google/callback")
async def google_callback(code: str, response: Response):
    """Google OAuth 콜백 처리"""
    try:
        if not code:
            raise HTTPException(status_code=400, detail="인증 코드가 없습니다.")
        
        # 1. 인증 코드를 액세스 토큰으로 교환
        token_data = await exchange_code_for_token(code)
        if not token_data:
            raise HTTPException(status_code=400, detail="토큰 교환에 실패했습니다.")
        
        access_token = token_data.get('access_token')
        if not access_token:
            raise HTTPException(status_code=400, detail="액세스 토큰을 받지 못했습니다.")
        
        # 2. 액세스 토큰으로 사용자 정보 가져오기
        google_user = await get_google_user_info(access_token)
        if not google_user:
            raise HTTPException(status_code=400, detail="사용자 정보를 가져오지 못했습니다.")
        
        # 3. 사용자 정보로 로컬 사용자 생성/업데이트
        user = create_or_update_user_from_google(google_user)
        if not user:
            raise HTTPException(status_code=500, detail="사용자 생성/업데이트에 실패했습니다.")
        
        # 4. JWT 토큰 생성
        from datetime import timedelta
        access_token_jwt = create_access_token(
            {"sub": str(user["id"])}, 
            expires_delta=timedelta(minutes=30)
        )
        
        # 5. 리프레시 토큰 생성
        refresh_raw, _, _ = create_refresh_token_for_user(
            user_id=user["id"], 
            device_info="Google OAuth"
        )
        
        # 6. 쿠키 설정
        response.set_cookie(
            key="captcha_token",
            value=access_token_jwt,
            domain=".realcatcha.com",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=60 * 30  # 30분
        )
        
        response.set_cookie(
            key="captcha_refresh",
            value=refresh_raw,
            domain=".realcatcha.com",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=60 * 60 * 24 * 14  # 14일
        )
        
        # 7. 프론트엔드로 리디렉트
        return {
            "success": True,
            "message": "Google 로그인이 완료되었습니다.",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "username": user["username"],
                "name": user.get("name"),
                "is_admin": user["is_admin"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google OAuth 처리 실패: {e}")

# ===== Me / Profile =====
from pydantic import BaseModel

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None


@router.put("/auth/me")
def update_me(req: UpdateProfileRequest, request: Request):
    """사용자 본인 프로필 업데이트 (현재는 name만)."""
    try:
        user = get_current_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        if req.name is None or len(req.name.strip()) == 0:
            raise HTTPException(status_code=400, detail="이름은 비워둘 수 없습니다.")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET name=%s WHERE id=%s", (req.name.strip(), user["id"]))
                cursor.execute(
                    "SELECT id, email, username, name, is_admin FROM users WHERE id=%s",
                    (user["id"],),
                )
                row = cursor.fetchone()
                updated = {
                    "id": row[0] if not isinstance(row, dict) else row.get("id"),
                    "email": row[1] if not isinstance(row, dict) else row.get("email"),
                    "username": row[2] if not isinstance(row, dict) else row.get("username"),
                    "name": row[3] if not isinstance(row, dict) else row.get("name"),
                    "is_admin": row[4] if not isinstance(row, dict) else row.get("is_admin"),
                }
                return {"success": True, "user": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프로필 업데이트 중 오류: {e}")


@router.delete("/auth/me")
def delete_me(response: Response, request: Request):
    """사용자 본인 탈퇴 (soft delete: is_active = FALSE) 및 리프레시 토큰 회수."""
    try:
        user = get_current_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (user["id"],))
                try:
                    cursor.execute("UPDATE refresh_tokens SET is_revoked=TRUE WHERE user_id=%s", (user["id"],))
                except Exception:
                    pass

        response.delete_cookie(key="captcha_token", domain=".realcatcha.com", samesite="none", secure=True)
        response.delete_cookie(key="captcha_refresh", domain=".realcatcha.com", samesite="none", secure=True)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원 탈퇴 처리 중 오류: {e}")
