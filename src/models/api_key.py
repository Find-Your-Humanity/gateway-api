from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import uuid
import hashlib
import secrets

from ..config.database import Base

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(String(50), unique=True, index=True, nullable=False)  # API 키 ID (접두사)
    secret_key = Column(String(255), nullable=False)  # 실제 API 키 (해시된 값)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)  # API 키 이름 (사용자가 지정)
    description = Column(Text, nullable=True)  # API 키 설명
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # 만료일 (선택사항)
    last_used_at = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0)
    
    # 권한 설정
    allowed_origins = Column(Text, nullable=True)  # JSON 형태로 허용 도메인 저장
    rate_limit_per_minute = Column(Integer, default=100)  # 분당 요청 제한
    rate_limit_per_day = Column(Integer, default=10000)  # 일일 요청 제한
    
    # 관계 설정 (User 모델이 별도로 정의되지 않았으므로 제거)
    # user = relationship("User", back_populates="api_keys")
    
    @classmethod
    def generate_key(cls, user_id: int, name: str, description: str = None, 
                    expires_at: datetime = None, allowed_origins: list = None,
                    rate_limit_per_minute: int = 100, rate_limit_per_day: int = 10000):
        """새로운 API 키 생성"""
        # 키 ID 생성 (접두사 + 랜덤 문자열)
        key_id = f"rc_{secrets.token_hex(8)}"
        
        # 실제 API 키 생성 (더 긴 랜덤 문자열)
        secret_key = secrets.token_hex(32)
        
        # API 키 생성
        api_key = cls(
            key_id=key_id,
            secret_key=cls._hash_secret(secret_key),
            user_id=user_id,
            name=name,
            description=description,
            expires_at=expires_at,
            allowed_origins=cls._serialize_origins(allowed_origins) if allowed_origins else None,
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_day=rate_limit_per_day
        )
        
        return api_key, secret_key  # 해시되지 않은 원본 키도 반환
    
    @classmethod
    def _hash_secret(cls, secret: str) -> str:
        """API 키를 해시하여 저장"""
        return hashlib.sha256(secret.encode()).hexdigest()
    
    @classmethod
    def _serialize_origins(cls, origins: list) -> str:
        """허용 도메인 리스트를 JSON 문자열로 직렬화"""
        import json
        return json.dumps(origins)
    
    def get_allowed_origins(self) -> list:
        """허용 도메인 리스트 반환"""
        if not self.allowed_origins:
            return []
        import json
        try:
            return json.loads(self.allowed_origins)
        except:
            return []
    
    def is_expired(self) -> bool:
        """API 키 만료 여부 확인"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """API 키 유효성 검사"""
        return self.is_active and not self.is_expired()
    
    def update_usage(self):
        """사용량 업데이트"""
        self.last_used_at = datetime.utcnow()
        self.usage_count += 1
