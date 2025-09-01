import os

# Google OAuth 설정
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'https://www.realcatcha.com/auth/google/callback')

# Google OAuth URL
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# OAuth 스코프
GOOGLE_SCOPES = [
    "openid",
    "email", 
    "profile"
]

def get_google_auth_url():
    """Google OAuth 로그인 URL 생성"""
    import urllib.parse
    
    params = {
        'response_type': 'code',
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'scope': ' '.join(GOOGLE_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent'
    }
    
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
