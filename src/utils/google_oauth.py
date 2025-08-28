import httpx
import json
from typing import Optional, Dict, Any
from src.config.oauth import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_URL, GOOGLE_USERINFO_URL

async def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
    """인증 코드를 액세스 토큰으로 교환"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    'client_id': GOOGLE_CLIENT_ID,
                    'client_secret': GOOGLE_CLIENT_SECRET,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': 'https://realcatcha.com/auth/google/callback'
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"토큰 교환 실패: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        print(f"토큰 교환 중 오류: {e}")
        return None

async def get_google_user_info(access_token: str) -> Optional[Dict[str, Any]]:
    """액세스 토큰으로 사용자 정보 가져오기"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"사용자 정보 가져오기 실패: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        print(f"사용자 정보 가져오기 중 오류: {e}")
        return None

def create_or_update_user_from_google(google_user: Dict[str, Any]) -> Dict[str, Any]:
    """Google 사용자 정보로 로컬 사용자 생성/업데이트"""
    from src.config.database import get_db_connection
    from src.utils.auth import get_password_hash
    import secrets
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # 기존 사용자 확인 (email 또는 google_id로)
            cursor.execute(
                "SELECT * FROM users WHERE email = %s OR google_id = %s",
                (google_user['email'], google_user['id'])
            )
            existing_user = cursor.fetchone()
            
            if existing_user:
                # 기존 사용자 업데이트
                cursor.execute(
                    """
                    UPDATE users 
                    SET google_id = %s, oauth_provider = 'google', 
                        name = COALESCE(%s, name), 
                        is_verified = TRUE
                    WHERE id = %s
                    """,
                    (google_user['id'], google_user.get('name'), existing_user['id'])
                )
                conn.commit()
                
                # 업데이트된 사용자 정보 반환
                cursor.execute("SELECT * FROM users WHERE id = %s", (existing_user['id'],))
                user_data = cursor.fetchone()
                
                # 딕셔너리 형태로 변환
                if isinstance(user_data, tuple):
                    # 컬럼명 가져오기
                    cursor.execute("DESCRIBE users")
                    columns = [col[0] for col in cursor.fetchall()]
                    user_data = dict(zip(columns, user_data))
                
                # Google OAuth는 name 필드 그대로 사용
                return user_data
            else:
                # 새 사용자 생성
                # 임시 비밀번호 생성 (Google OAuth 사용자는 비밀번호로 로그인하지 않음)
                temp_password = secrets.token_urlsafe(32)
                password_hash = get_password_hash(temp_password)
                
                cursor.execute(
                    """
                    INSERT INTO users (email, username, password_hash, name, google_id, oauth_provider, is_verified, plan_id)
                    VALUES (%s, %s, %s, %s, %s, 'google', TRUE, 1)
                    """,
                    (
                        google_user['email'],
                        google_user['email'].split('@')[0],  # 이메일 앞부분을 username으로
                        password_hash,
                        google_user.get('name', ''),
                        google_user['id']
                    )
                )
                
                user_id = cursor.lastrowid
                conn.commit()
                
                # 생성된 사용자 정보 반환
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                user_data = cursor.fetchone()
                
                # 딕셔너리 형태로 변환
                if isinstance(user_data, tuple):
                    # 컬럼명 가져오기
                    cursor.execute("DESCRIBE users")
                    columns = [col[0] for col in cursor.fetchall()]
                    user_data = dict(zip(columns, user_data))
                
                # Google OAuth는 name 필드 그대로 사용
                return user_data
