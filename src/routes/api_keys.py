from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional, Dict
import secrets
import hashlib
from datetime import datetime, timedelta
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

router = APIRouter(prefix="/api", tags=["API Keys"])

class APIKeyService:
    def __init__(self, db_connection):
        self.db = db_connection
    
    def generate_api_key(self, user_id: int, name: str, description: str = None) -> Dict:
        """새로운 API 키 생성"""
        try:
            # API 키 생성
            key_id = f"rc_live_{secrets.token_hex(16)}"
            secret_key = f"rc_sk_{secrets.token_hex(32)}"
            
            # DB에 저장
            query = """
            INSERT INTO api_keys (key_id, secret_key, user_id, name, description, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            self.db.execute(query, (key_id, secret_key, user_id, name, description, True, datetime.now()))
            
            return {
                "success": True,
                "api_key": key_id,
                "secret_key": secret_key,
                "created_at": datetime.now().isoformat()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API 키 생성 실패: {str(e)}")
    
    def get_user_api_keys(self, user_id: int) -> List[Dict]:
        """사용자의 API 키 목록 조회"""
        try:
            query = """
            SELECT id, key_id, name, description, is_active, created_at, updated_at, last_used_at, usage_count
            FROM api_keys
            WHERE user_id = %s
            ORDER BY created_at DESC
            """
            results = self.db.fetch_all(query, (user_id,))
            
            api_keys = []
            for row in results:
                api_keys.append({
                    "id": row['id'],
                    "key_id": row['key_id'],
                    "name": row['name'],
                    "description": row['description'],
                    "is_active": bool(row['is_active']),
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None,
                    "last_used_at": row['last_used_at'].isoformat() if row['last_used_at'] else None,
                    "usage_count": row['usage_count'] or 0
                })
            
            return api_keys
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API 키 목록 조회 실패: {str(e)}")
    
    def toggle_api_key(self, user_id: int, key_id: str, is_active: bool) -> Dict:
        """API 키 활성화/비활성화"""
        try:
            query = """
            UPDATE api_keys 
            SET is_active = %s
            WHERE key_id = %s AND user_id = %s
            """
            result = self.db.execute(query, (is_active, key_id, user_id))
            
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
            
            return {
                "success": True,
                "message": f"API 키가 {'활성화' if is_active else '비활성화'}되었습니다"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API 키 상태 변경 실패: {str(e)}")
    
    def delete_api_key(self, user_id: int, key_id: str) -> Dict:
        """API 키 삭제"""
        try:
            query = """
            DELETE FROM api_keys 
            WHERE key_id = %s AND user_id = %s
            """
            result = self.db.execute(query, (key_id, user_id))
            
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
            
            return {
                "success": True,
                "message": "API 키가 삭제되었습니다"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API 키 삭제 실패: {str(e)}")

from pydantic import BaseModel

class CreateApiKeyRequest(BaseModel):
    name: str
    description: Optional[str] = None

@router.post("/keys/create")
async def create_api_key(
    request_data: CreateApiKeyRequest,
    current_user: Dict = Depends(get_current_user_from_request)
):
    """새로운 API 키 생성"""
    try:
        with get_db_connection() as db:
            api_key_service = APIKeyService(db)
            result = api_key_service.generate_api_key(
                user_id=current_user['id'],
                name=request_data.name,
                description=request_data.description
            )
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/keys/test-db")
async def test_api_keys_database():
    """API 키 데이터베이스 테스트"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. api_keys 테이블 존재 확인
                cursor.execute("SHOW TABLES LIKE 'api_keys'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    return {
                        "success": False,
                        "error": "api_keys 테이블이 존재하지 않습니다",
                        "tables": []
                    }
                
                # 2. api_keys 테이블 구조 확인
                cursor.execute("DESCRIBE api_keys")
                columns = cursor.fetchall()
                
                # 3. api_keys 테이블 데이터 확인
                cursor.execute("SELECT COUNT(*) as count FROM api_keys")
                count_result = cursor.fetchone()
                
                return {
                    "success": True,
                    "table_exists": True,
                    "columns": columns,
                    "total_records": count_result['count'] if count_result else 0
                }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@router.get("/keys/list")
async def get_api_keys(current_user: Dict = Depends(get_current_user_from_request)):
    """사용자의 API 키 목록 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 직접 쿼리로 테스트
                query = """
                SELECT id, key_id, name, description, is_active, created_at, updated_at, last_used_at, usage_count
                FROM api_keys
                WHERE user_id = %s
                ORDER BY created_at DESC
                """
                cursor.execute(query, (current_user['id'],))
                results = cursor.fetchall()
                
                api_keys = []
                for row in results:
                    api_keys.append({
                        "id": row['id'],
                        "key_id": row['key_id'],
                        "name": row['name'],
                        "description": row['description'],
                        "is_active": bool(row['is_active']),
                        "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                        "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None,
                        "last_used_at": row['last_used_at'].isoformat() if row['last_used_at'] else None,
                        "usage_count": row['usage_count'] or 0
                    })
                
                return {
                    "success": True,
                    "api_keys": api_keys
                }
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"API 키 목록 조회 실패: {str(e)}\n{traceback.format_exc()}")

class ToggleApiKeyRequest(BaseModel):
    is_active: bool

@router.patch("/keys/{key_id}/toggle")
async def toggle_api_key(
    key_id: str,
    request_data: ToggleApiKeyRequest,
    current_user: Dict = Depends(get_current_user_from_request)
):
    """API 키 활성화/비활성화"""
    try:
        with get_db_connection() as db:
            api_key_service = APIKeyService(db)
            result = api_key_service.toggle_api_key(
                user_id=current_user['id'],
                key_id=key_id,
                is_active=request_data.is_active
            )
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: Dict = Depends(get_current_user_from_request)
):
    """API 키 삭제"""
    try:
        with get_db_connection() as db:
            api_key_service = APIKeyService(db)
            result = api_key_service.delete_api_key(
                user_id=current_user['id'],
                key_id=key_id
            )
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
