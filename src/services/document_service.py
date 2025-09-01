import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import HTTPException

class DocumentService:
    def __init__(self):
        # 문서 저장소 기본 경로
        self.documents_dir = Path(__file__).parent.parent.parent / "documents"
        self.documents_dir.mkdir(exist_ok=True)
        
        # 지원하는 언어
        self.supported_languages = ["ko", "en"]
        
        # 지원하는 문서 타입
        self.supported_document_types = [
            "developer_guide",
            "api_reference", 
            "integration_guide"
        ]
    
    def _validate_language(self, language: str) -> bool:
        """언어 유효성 검사"""
        return language in self.supported_languages
    
    def _validate_document_type(self, document_type: str) -> bool:
        """문서 타입 유효성 검사"""
        return document_type in self.supported_document_types
    
    def _get_document_path(self, language: str, document_type: str) -> Path:
        """문서 파일 경로 생성"""
        if not self._validate_language(language):
            raise HTTPException(status_code=400, detail=f"지원하지 않는 언어: {language}")
        
        if not self._validate_document_type(document_type):
            raise HTTPException(status_code=400, detail=f"지원하지 않는 문서 타입: {document_type}")
        
        # 언어별 디렉토리 생성
        lang_dir = self.documents_dir / language
        lang_dir.mkdir(exist_ok=True)
        
        return lang_dir / f"{document_type}.md"
    
    async def get_document(self, language: str, document_type: str) -> Dict[str, Any]:
        """문서 내용 조회"""
        try:
            doc_path = self._get_document_path(language, document_type)
            
            if not doc_path.exists():
                # 파일이 없으면 기본 내용 반환
                return {
                    "success": True,
                    "data": {
                        "content": "",
                        "language": language,
                        "document_type": document_type,
                        "exists": False
                    }
                }
            
            # 파일 내용 읽기
            with open(doc_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "data": {
                    "content": content,
                    "language": language,
                    "document_type": document_type,
                    "exists": True
                }
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"문서 조회 실패: {str(e)}")
    
    async def update_document(self, language: str, document_type: str, content: str) -> Dict[str, Any]:
        """문서 내용 업데이트"""
        try:
            doc_path = self._get_document_path(language, document_type)
            
            # 디렉토리가 없으면 생성
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 파일에 내용 쓰기
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "data": {
                    "message": "문서가 성공적으로 저장되었습니다.",
                    "language": language,
                    "document_type": document_type,
                    "file_path": str(doc_path)
                }
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"문서 저장 실패: {str(e)}")
    
    async def list_documents(self, language: str = None) -> Dict[str, Any]:
        """문서 목록 조회"""
        try:
            documents = []
            
            if language:
                # 특정 언어의 문서만 조회
                if not self._validate_language(language):
                    raise HTTPException(status_code=400, detail=f"지원하지 않는 언어: {language}")
                
                lang_dir = self.documents_dir / language
                if lang_dir.exists():
                    for doc_file in lang_dir.glob("*.md"):
                        documents.append({
                            "name": doc_file.stem,
                            "language": language,
                            "path": str(doc_file),
                            "exists": True
                        })
            else:
                # 모든 언어의 문서 조회
                for lang in self.supported_languages:
                    lang_dir = self.documents_dir / lang
                    if lang_dir.exists():
                        for doc_file in lang_dir.glob("*.md"):
                            documents.append({
                                "name": doc_file.stem,
                                "language": lang,
                                "path": str(doc_file),
                                "exists": True
                            })
            
            return {
                "success": True,
                "data": {
                    "documents": documents,
                    "total": len(documents)
                }
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"문서 목록 조회 실패: {str(e)}")

# 전역 인스턴스 생성
document_service = DocumentService() 