import os
import jwt
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