from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from src.services.document_service import document_service
from src.utils.auth import get_current_user, verify_admin_permission

router = APIRouter(prefix="/api/admin", tags=["admin_documents"])

# 요청/응답 모델
class DocumentUpdateRequest(BaseModel):
    language: str
    document_type: str
    content: str

class DocumentResponse(BaseModel):
    success: bool
    data: dict

# 관리자 권한 확인 의존성
async def require_admin(user = Depends(get_current_user)):
    if not verify_admin_permission(user):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user

@router.get("/documents/{language}/{document_type}", response_model=DocumentResponse)
async def get_document(
    language: str,
    document_type: str
):
    """문서 내용 조회 (공개 엔드포인트)"""
    print(f"🔍 API 요청 수신: language={language}, document_type={document_type}")
    try:
        result = await document_service.get_document(language, document_type)
        print(f"🔍 API 응답 성공: {result}")
        return result
    except HTTPException:
        print(f"🔍 API HTTP 오류 발생: {HTTPException}")
        raise
    except Exception as e:
        print(f"🔍 API 일반 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"문서 조회 중 오류 발생: {str(e)}")

@router.post("/documents/update", response_model=DocumentResponse)
async def update_document(
    request: DocumentUpdateRequest,
    current_user = Depends(require_admin)
):
    """문서 내용 업데이트 (관리자 전용)"""
    try:
        result = await document_service.update_document(
            request.language,
            request.document_type,
            request.content
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 업데이트 중 오류 발생: {str(e)}")

@router.get("/documents", response_model=DocumentResponse)
async def list_documents(
    language: Optional[str] = None
):
    """문서 목록 조회 (공개 엔드포인트)"""
    try:
        result = await document_service.list_documents(language)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 목록 조회 중 오류 발생: {str(e)}")

@router.get("/documents/health")
async def documents_health_check():
    """문서 서비스 상태 확인 (공개 엔드포인트)"""
    try:
        # 간단한 상태 확인
        return {
            "success": True,
            "data": {
                "service": "admin_documents",
                "status": "healthy",
                "supported_languages": document_service.supported_languages,
                "supported_document_types": document_service.supported_document_types
            }
        }
    except Exception as e:
        return {
            "success": False,
            "data": {
                "service": "admin_documents",
                "status": "unhealthy",
                "error": str(e)
            }
        } 