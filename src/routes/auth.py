from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta
from src.utils.auth import (
    authenticate_user, 
    create_access_token, 
    verify_token, 
    get_user_by_id,
    create_user
)
from src.config.database import init_database

router = APIRouter(prefix="/api/auth", tags=["authentication"])
security = HTTPBearer()

# 요청 모델
class LoginRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    contact: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_admin: bool

# 의존성 함수
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """현재 인증된 사용자 정보 반환"""
    token = credentials.credentials
    payload = verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 정보가 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_user_by_id(int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """사용자 로그인"""
    user = authenticate_user(request.email, request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 액세스 토큰 생성
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": str(user["id"])}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    """사용자 회원가입"""
    # 새 사용자 생성
    user, err = create_user(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        contact=request.contact
    )
    
    if err:
        message_map = {
            'email_exists': '이미 존재하는 이메일입니다.',
            'username_exists': '이미 존재하는 사용자명입니다.',
            'contact_exists': '이미 등록된 연락처입니다.',
            'error': '회원가입 처리 중 오류가 발생했습니다.'
        }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message_map.get(err, '회원가입에 실패했습니다.')
        )
    
    # 액세스 토큰 생성
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": str(user["id"])}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """현재 사용자 정보 조회"""
    return current_user

@router.post("/refresh")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """토큰 갱신"""
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": str(current_user["id"])}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """로그아웃 (클라이언트에서 토큰 삭제)"""
    return {"message": "로그아웃되었습니다."}

# 데이터베이스 초기화 엔드포인트 (개발용)
@router.post("/init-db")
async def initialize_database():
    """데이터베이스 초기화 (개발용)"""
    try:
        init_database()
        return {"message": "데이터베이스가 성공적으로 초기화되었습니다."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 초기화 실패: {str(e)}"
        ) 