from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
import hashlib
from datetime import datetime, timedelta
import json

from ..models.api_key import APIKey
from ..config.database import get_db

security = HTTPBearer()

class RateLimiter:
    """간단한 메모리 기반 레이트 리미터"""
    
    def __init__(self):
        self.requests = {}  # key_id -> [(timestamp, count), ...]
    
    def is_allowed(self, key_id: str, limit_per_minute: int, limit_per_day: int) -> bool:
        now = datetime.utcnow()
        
        if key_id not in self.requests:
            self.requests[key_id] = []
        
        # 오래된 요청 기록 제거
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)
        
        self.requests[key_id] = [
            (ts, count) for ts, count in self.requests[key_id]
            if ts > minute_ago
        ]
        
        # 분당 요청 수 확인
        minute_count = sum(count for _, count in self.requests[key_id])
        if minute_count >= limit_per_minute:
            return False
        
        # 일일 요청 수 확인 (실제로는 Redis나 DB 사용 권장)
        day_requests = [
            (ts, count) for ts, count in self.requests[key_id]
            if ts > day_ago
        ]
        day_count = sum(count for _, count in day_requests)
        if day_count >= limit_per_day:
            return False
        
        # 요청 기록 추가
        self.requests[key_id].append((now, 1))
        return True

# 전역 레이트 리미터 인스턴스
rate_limiter = RateLimiter()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> APIKey:
    """API 키 검증"""
    
    if not credentials or not credentials.scheme.lower() == "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header. Use 'Bearer <api_key>'"
        )
    
    api_key = credentials.credentials
    
    # API 키 형식 검증 (rc_ 접두사 확인)
    if not api_key.startswith("rc_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format"
        )
    
    # 키 ID와 시크릿 분리
    try:
        key_id = api_key[:18]  # rc_ + 16자리 hex
        secret_part = api_key[18:]
    except:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format"
        )
    
    # DB에서 API 키 조회
    db_api_key = db.query(APIKey).filter(APIKey.key_id == key_id).first()
    if not db_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key not found"
        )
    
    # 시크릿 키 검증
    expected_hash = hashlib.sha256(secret_part.encode()).hexdigest()
    if db_api_key.secret_key != expected_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    # API 키 유효성 검사
    if not db_api_key.is_valid():
        raise HTTPException(
            status_code=401,
            detail="API key is inactive or expired"
        )
    
    # 레이트 리밋 확인
    if not rate_limiter.is_allowed(
        key_id, 
        db_api_key.rate_limit_per_minute, 
        db_api_key.rate_limit_per_day
    ):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )
    
    # 사용량 업데이트
    db_api_key.update_usage()
    db.commit()
    
    return db_api_key

async def verify_origin(
    request: Request,
    api_key: APIKey = Depends(verify_api_key)
) -> APIKey:
    """Origin 검증 (CORS 대체)"""
    
    # 허용된 origin이 없으면 모든 origin 허용
    allowed_origins = api_key.get_allowed_origins()
    if not allowed_origins:
        return api_key
    
    # Origin 헤더 확인
    origin = request.headers.get("origin")
    if not origin:
        # Origin이 없으면 Referer 헤더에서 추출 시도
        referer = request.headers.get("referer")
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"
    
    if not origin:
        raise HTTPException(
            status_code=403,
            detail="Origin header required"
        )
    
    # Origin 검증
    if origin not in allowed_origins:
        raise HTTPException(
            status_code=403,
            detail=f"Origin '{origin}' not allowed for this API key"
        )
    
    return api_key
