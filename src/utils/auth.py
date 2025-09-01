import os
import jwt
from datetime import datetime, timedelta
import secrets
import hashlib
from passlib.context import CryptContext
from typing import Optional, Dict, Any, Tuple
from src.config.database import get_db_connection
from fastapi import Request

# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 설정
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """비밀번호 해싱"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWT 액세스 토큰 생성"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """JWT 토큰 검증"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def _hash_refresh(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_refresh_token_for_user(user_id: int, device_info: Optional[str] = None) -> Tuple[str, str, datetime]:
    """Create a refresh token for a user.
    Returns (raw_token, token_hash, expires_at)
    """
    raw = secrets.token_urlsafe(64)
    token_hash = _hash_refresh(raw)
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO refresh_tokens (user_id, token_hash, expires_at, device_info, last_used_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, token_hash, expires_at, device_info, datetime.utcnow()),
                )
        return raw, token_hash, expires_at
    except Exception as e:
        print(f"리프레시 토큰 생성 오류: {e}")
        raise


def verify_and_rotate_refresh_token(raw_token: str, rotate: bool = True, device_info: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Verify refresh token by hash. Optionally rotate (rolling refresh). Returns {user_id} on success."""
    token_hash = _hash_refresh(raw_token)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, expires_at, is_revoked FROM refresh_tokens
                    WHERE token_hash=%s
                    """,
                    (token_hash,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                # tuple/dict safe access
                _id = row[0] if not isinstance(row, dict) else row["id"]
                user_id = row[1] if not isinstance(row, dict) else row["user_id"]
                expires_at = row[2] if not isinstance(row, dict) else row["expires_at"]
                is_revoked = row[3] if not isinstance(row, dict) else row["is_revoked"]

                if is_revoked:
                    return None
                if expires_at <= datetime.utcnow():
                    return None

                # update last_used_at
                cursor.execute("UPDATE refresh_tokens SET last_used_at=%s WHERE id=%s", (datetime.utcnow(), _id))

                if rotate:
                    # revoke current and issue a new one
                    cursor.execute("UPDATE refresh_tokens SET is_revoked=TRUE WHERE id=%s", (_id,))
                    new_raw, new_hash, new_exp = create_refresh_token_for_user(user_id, device_info)
                    return {"user_id": user_id, "new_refresh_raw": new_raw, "new_refresh_expires": new_exp}

                return {"user_id": user_id}
    except Exception as e:
        print(f"리프레시 토큰 검증 오류: {e}")
        return None

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """사용자 인증"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE email = %s AND is_active = TRUE AND is_verified = TRUE",
                    (email,)
                )
                user = cursor.fetchone()
                
                if user and verify_password(password, user['password_hash']):
                    return {
                        'id': user['id'],
                        'email': user['email'],
                        'username': user['username'],
                        'name': user['username'],  # ← 일반 로그인은 username을 name으로 반환
                        'is_admin': user['is_admin']
                    }
                return None
    except Exception as e:
        print(f"사용자 인증 오류: {e}")
        return None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """사용자 ID로 사용자 정보 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, email, username, name, oauth_provider, is_admin FROM users WHERE id = %s AND is_active = TRUE",
                    (user_id,)
                )
                user = cursor.fetchone()
                if user:
                    # OAuth 사용자는 name, 일반 사용자는 username을 name으로 설정
                    if user.get('oauth_provider') != 'google':
                        user['name'] = user.get('username')
                return user
    except Exception as e:
        print(f"사용자 조회 오류: {e}")
        return None

def create_user(email: str, username: str, password: str, full_name: str = None, contact: str = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """새 사용자 생성. 성공 시 (user, None) 반환, 실패 시 (None, 'email_exists'|'username_exists'|'contact_exists'|'error') 반환"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 이메일 중복 확인
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    return None, 'email_exists'
                
                # 사용자명 중복 확인
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    return None, 'username_exists'
                
                # 연락처 중복 확인 (값이 있을 때만)
                if contact:
                    cursor.execute("SELECT id FROM users WHERE contact = %s", (contact,))
                    if cursor.fetchone():
                        return None, 'contact_exists'
                
                # 비밀번호 해싱
                hashed_password = get_password_hash(password)
                
                # 사용자 생성 (name, contact 컬럼 사용)
                cursor.execute(
                    """
                    INSERT INTO users (email, username, password_hash, name, contact, is_verified)
                    VALUES (%s, %s, %s, %s, %s, FALSE)
                    """,
                    (email, username, hashed_password, full_name, contact)
                )
                
                user_id = cursor.lastrowid
                
                return {
                    'id': user_id,
                    'email': email,
                    'username': username,
                    'name': username,  # ← 일반 회원가입은 username을 name으로 반환
                    'contact': contact,
                    'is_admin': False,
                    'is_verified': False
                }, None
    except Exception as e:
        print(f"사용자 생성 오류: {e}")
        return None, 'error'

# FastAPI 의존성 함수들
def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """현재 인증된 사용자 정보 반환"""
    try:
        # 쿠키에서 토큰 가져오기 (Google OAuth에서 설정한 쿠키 이름 사용)
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
        user = get_user_by_id(user_id)
        return user
    except Exception as e:
        print(f"현재 사용자 조회 오류: {e}")
        return None

def verify_admin_permission(user: Dict[str, Any]) -> bool:
    """사용자가 관리자 권한을 가지고 있는지 확인"""
    if not user:
        return False
    
    # is_admin이 True이거나 1인 경우 관리자로 간주
    return user.get('is_admin') == True or user.get('is_admin') == 1 