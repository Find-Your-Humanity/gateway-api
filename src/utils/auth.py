import os
import jwt
import secrets
import hashlib
from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional, Dict, Any, Tuple
from src.config.database import get_db_connection

# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 설정
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 14

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
                        'full_name': user.get('full_name') if isinstance(user, dict) else None,
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
                    "SELECT id, email, username, name as full_name, is_admin FROM users WHERE id = %s AND is_active = TRUE",
                    (user_id,)
                )
                user = cursor.fetchone()
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
                    'full_name': full_name,
                    'contact': contact,
                    'is_admin': False,
                    'is_verified': False
                }, None
    except Exception as e:
        print(f"사용자 생성 오류: {e}")
        return None, 'error'

def create_refresh_token(user_id: int, device_info: str = None) -> str:
    """Refresh Token 생성 및 데이터베이스 저장"""
    try:
        # 랜덤 토큰 생성
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 기존 활성 토큰들 무효화 (선택적: 단일 세션만 허용하려면)
                # cursor.execute(
                #     "UPDATE refresh_tokens SET is_revoked = TRUE WHERE user_id = %s AND is_revoked = FALSE",
                #     (user_id,)
                # )
                
                # 새 Refresh Token 저장
                cursor.execute(
                    """
                    INSERT INTO refresh_tokens (user_id, token_hash, expires_at, device_info, last_used_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, token_hash, expires_at, device_info, datetime.utcnow())
                )
        
        return raw_token
    except Exception as e:
        print(f"Refresh Token 생성 오류: {e}")
        return None

def verify_refresh_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh Token 검증 및 사용자 정보 반환"""
    try:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Refresh Token 및 사용자 정보 조회
                cursor.execute(
                    """
                    SELECT rt.id, rt.user_id, rt.expires_at, rt.is_revoked,
                           u.id, u.email, u.username, u.name, u.is_admin
                    FROM refresh_tokens rt
                    JOIN users u ON rt.user_id = u.id
                    WHERE rt.token_hash = %s AND rt.is_revoked = FALSE AND u.is_active = TRUE
                    """,
                    (token_hash,)
                )
                result = cursor.fetchone()
                
                if not result:
                    return None
                
                # 만료 확인
                expires_at = result['expires_at'] if isinstance(result, dict) else result[2]
                if datetime.utcnow() > expires_at:
                    # 만료된 토큰 무효화
                    cursor.execute(
                        "UPDATE refresh_tokens SET is_revoked = TRUE WHERE token_hash = %s",
                        (token_hash,)
                    )
                    return None
                
                # 마지막 사용 시간 업데이트
                cursor.execute(
                    "UPDATE refresh_tokens SET last_used_at = %s WHERE token_hash = %s",
                    (datetime.utcnow(), token_hash)
                )
                
                # 사용자 정보 반환
                if isinstance(result, dict):
                    return {
                        'id': result['user_id'],
                        'email': result['email'],
                        'username': result['username'],
                        'full_name': result['name'],
                        'is_admin': result['is_admin']
                    }
                else:
                    return {
                        'id': result[1],
                        'email': result[5],
                        'username': result[6],
                        'full_name': result[7],
                        'is_admin': result[8]
                    }
    except Exception as e:
        print(f"Refresh Token 검증 오류: {e}")
        return None

def revoke_refresh_token(refresh_token: str) -> bool:
    """Refresh Token 무효화"""
    try:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE refresh_tokens SET is_revoked = TRUE WHERE token_hash = %s",
                    (token_hash,)
                )
                return cursor.rowcount > 0
    except Exception as e:
        print(f"Refresh Token 무효화 오류: {e}")
        return False

def revoke_all_user_refresh_tokens(user_id: int) -> bool:
    """사용자의 모든 Refresh Token 무효화 (로그아웃 시 사용)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE refresh_tokens SET is_revoked = TRUE WHERE user_id = %s AND is_revoked = FALSE",
                    (user_id,)
                )
                return True
    except Exception as e:
        print(f"사용자 Refresh Token 무효화 오류: {e}")
        return False

def cleanup_expired_refresh_tokens() -> int:
    """만료된 Refresh Token 정리 (정기 정리 작업용)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE refresh_tokens SET is_revoked = TRUE WHERE expires_at < %s AND is_revoked = FALSE",
                    (datetime.utcnow(),)
                )
                return cursor.rowcount
    except Exception as e:
        print(f"만료된 Refresh Token 정리 오류: {e}")
        return 0 