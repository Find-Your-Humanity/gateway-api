from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..models.api_key import APIKey
from ..config.database import get_db
from .auth import get_current_user_from_request as get_current_user

router = APIRouter(prefix="/api/keys", tags=["API Keys"])

# Pydantic 모델
class APIKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    expires_at: Optional[datetime] = None
    allowed_origins: Optional[List[str]] = None
    rate_limit_per_minute: Optional[int] = 100
    rate_limit_per_day: Optional[int] = 10000

class APIKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_origins: Optional[List[str]] = None
    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_day: Optional[int] = None

class APIKeyResponse(BaseModel):
    id: int
    key_id: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int
    allowed_origins: Optional[List[str]]
    rate_limit_per_minute: int
    rate_limit_per_day: int

    class Config:
        from_attributes = True

class APIKeyCreateResponse(BaseModel):
    api_key: str  # 전체 API 키 (한 번만 표시)
    key_info: APIKeyResponse

@router.post("/", response_model=APIKeyCreateResponse)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """새로운 API 키 생성"""
    
    # 사용자별 API 키 개수 제한 (선택사항)
    existing_keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).count()
    if existing_keys >= 10:  # 최대 10개
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum number of API keys reached (10)"
        )
    
    # API 키 생성
    api_key, secret_key = APIKey.generate_key(
        user_id=current_user.id,
        name=key_data.name,
        description=key_data.description,
        expires_at=key_data.expires_at,
        allowed_origins=key_data.allowed_origins,
        rate_limit_per_minute=key_data.rate_limit_per_minute,
        rate_limit_per_day=key_data.rate_limit_per_day
    )
    
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    # 전체 API 키 조합 (key_id + secret_part)
    full_api_key = f"{api_key.key_id}{secret_key}"
    
    return APIKeyCreateResponse(
        api_key=full_api_key,
        key_info=APIKeyResponse.from_orm(api_key)
    )

@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자의 API 키 목록 조회"""
    
    api_keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).all()
    return [APIKeyResponse.from_orm(key) for key in api_keys]

@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 API 키 조회"""
    
    api_key = db.query(APIKey).filter(
        APIKey.key_id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return APIKeyResponse.from_orm(api_key)

@router.put("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    key_data: APIKeyUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API 키 정보 수정"""
    
    api_key = db.query(APIKey).filter(
        APIKey.key_id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # 업데이트할 필드들
    if key_data.name is not None:
        api_key.name = key_data.name
    if key_data.description is not None:
        api_key.description = key_data.description
    if key_data.is_active is not None:
        api_key.is_active = key_data.is_active
    if key_data.allowed_origins is not None:
        api_key.allowed_origins = APIKey._serialize_origins(key_data.allowed_origins)
    if key_data.rate_limit_per_minute is not None:
        api_key.rate_limit_per_minute = key_data.rate_limit_per_minute
    if key_data.rate_limit_per_day is not None:
        api_key.rate_limit_per_day = key_data.rate_limit_per_day
    
    db.commit()
    db.refresh(api_key)
    
    return APIKeyResponse.from_orm(api_key)

@router.delete("/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API 키 삭제"""
    
    api_key = db.query(APIKey).filter(
        APIKey.key_id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    db.delete(api_key)
    db.commit()
    
    return {"message": "API key deleted successfully"}

@router.post("/{key_id}/regenerate")
async def regenerate_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API 키 재생성 (기존 키 무효화 후 새 키 발급)"""
    
    api_key = db.query(APIKey).filter(
        APIKey.key_id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # 새 시크릿 키 생성
    import secrets
    new_secret = secrets.token_hex(32)
    api_key.secret_key = APIKey._hash_secret(new_secret)
    
    db.commit()
    db.refresh(api_key)
    
    # 전체 API 키 조합
    full_api_key = f"{api_key.key_id}{new_secret}"
    
    return {
        "message": "API key regenerated successfully",
        "api_key": full_api_key,
        "key_info": APIKeyResponse.from_orm(api_key)
    }
