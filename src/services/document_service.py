import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 모듈 내 print 호출을 로거로 매핑합니다.
# 규칙: '❌' 또는 '오류' 또는 'error' 포함 시 error, '⚠️' 포함 시 warning, 그 외 info

def _doc_print(*args, sep=" ", end="\n"):
    try:
        msg = sep.join(str(a) for a in args)
    except Exception:
        msg = " ".join(map(str, args))
    low = msg.lower()
    if ("❌" in msg) or ("오류" in msg) or ("error" in low):
        logger.error(msg)
    elif "⚠️" in msg:
        logger.warning(msg)
    else:
        logger.info(msg)

print = _doc_print

class DocumentService:
    def __init__(self):
        # 문서 저장소 경로
        self.documents_dir = Path(__file__).parent.parent.parent / "documents"
        self.supported_languages = ["ko", "en"]
        self.supported_document_types = [
            "developer_guide",
            "api_key_usage_guide", 
            "설정", 
            "invisible_captcha", 
            "custom_theme", 
            "language_codes", 
            "enterprise_account_management", 
            "recaptcha_migration", 
            "mobile_sdk", 
            "통합", 
            "pro_features", 
            "enterprise_overview"
        ]
        
        # 사이드바 아이템과 실제 파일명 매핑
        self.sidebar_to_filename_mapping = {
            "developer_guide": "developer_guide",
            "api_key_usage_guide": "api_key_usage_guide",
            "설정": "설정",
            "invisible_captcha": "invisible_captcha",
            "custom_theme": "custom_theme",
            "language_codes": "language_codes",
            "enterprise_account_management": "enterprise_account_management",
            "recaptcha_migration": "recaptcha_migration",
            "mobile_sdk": "mobile_sdk",
            "통합": "통합",
            "pro_features": "pro_features",
            "enterprise_overview": "enterprise_overview"
        }
        
        # 문서 저장소 초기화
        self._init_document_storage()
    
    def _init_document_storage(self):
        """문서 저장소 디렉토리 초기화"""
        for lang in self.supported_languages:
            lang_dir = self.documents_dir / lang
            lang_dir.mkdir(parents=True, exist_ok=True)
    
    def _normalize_document_type(self, document_type: str) -> str:
        """사이드바 아이템을 실제 파일명으로 변환"""
        # 직접 매핑 확인
        if document_type in self.sidebar_to_filename_mapping:
            return self.sidebar_to_filename_mapping[document_type]
        
        # 파일명 정규화 (언더스코어를 하이픈으로 변환 등)
        normalized = document_type.replace('_', '-').lower()
        
        # 정규화된 이름으로 매핑 확인
        for key, value in self.sidebar_to_filename_mapping.items():
            if key.replace('_', '-').lower() == normalized:
                return value
        
        # 매핑되지 않은 경우 원본 반환
        return document_type
    
    def _get_document_path(self, language: str, document_type: str) -> Path:
        """문서 파일 경로 반환"""
        # 사이드바 아이템을 실제 파일명으로 변환
        filename = self._normalize_document_type(document_type)
        print(f"🔍 파일명 정규화: {document_type} -> {filename}")
        
        doc_path = self.documents_dir / language / f"{filename}.md"
        print(f"🔍 최종 파일 경로: {doc_path}")
        print(f"🔍 문서 디렉토리: {self.documents_dir}")
        print(f"🔍 언어 디렉토리: {self.documents_dir / language}")
        
        return doc_path
    
    def _get_default_content(self, language: str, document_type: str) -> str:
        """기본 콘텐츠 반환"""
        return f"# {document_type.replace('_', ' ').title()}\n\nThis is the default content for {document_type} in {language}."
    
    async def get_document(self, language: str, document_type: str) -> Dict[str, Any]:
        """문서 내용 조회"""
        print(f"🔍 문서 서비스 호출: language={language}, document_type={document_type}")
        print(f"🔍 지원 언어: {self.supported_languages}")
        print(f"🔍 지원 문서 타입: {self.supported_document_types}")
        
        try:
            # 지원 언어 및 문서 타입 확인
            if language not in self.supported_languages:
                print(f"🔍 지원하지 않는 언어: {language}")
                return {
                    "success": False,
                    "data": {"error": f"Unsupported language: {language}"}
                }
            
            if document_type not in self.supported_document_types:
                print(f"🔍 지원하지 않는 문서 타입: {document_type}")
                return {
                    "success": False,
                    "data": {"error": f"Unsupported document type: {document_type}"}
                }
            
            # 문서 파일 경로
            doc_path = self._get_document_path(language, document_type)
            print(f"🔍 파일 경로: {doc_path}")
            print(f"🔍 파일 존재: {doc_path.exists()}")
            
            # 파일이 존재하면 읽기, 없으면 기본 콘텐츠 반환
            if doc_path.exists():
                print(f"🔍 파일 읽기 시작: {doc_path}")
                content = doc_path.read_text(encoding='utf-8')
                print(f"🔍 파일 읽기 성공, 내용 길이: {len(content)}")
                result = {
                    "success": True,
                    "data": {
                        "content": content,
                        "exists": True,
                        "file_path": str(doc_path),
                        "normalized_type": document_type
                    }
                }
            else:
                print(f"🔍 파일이 존재하지 않음, 기본 콘텐츠 반환")
                content = self._get_default_content(language, document_type)
                result = {
                    "success": True,
                    "data": {
                        "content": content,
                        "exists": False,
                        "file_path": str(doc_path),
                        "normalized_type": document_type
                    }
                }
            
            print(f"🔍 문서 서비스 응답: {result}")
            return result
            
        except Exception as e:
            print(f"🔍 문서 서비스 오류 발생: {str(e)}")
            import traceback
            print(f"🔍 오류 상세: {traceback.format_exc()}")
            return {
                "success": False,
                "data": {"error": f"문서 조회 중 오류 발생: {str(e)}"}
            }
    
    async def update_document(self, language: str, document_type: str, content: str) -> Dict[str, Any]:
        """문서 내용 업데이트"""
        print(f"🔍 문서 업데이트 서비스 호출: language={language}, document_type={document_type}")
        print(f"🔍 업데이트할 콘텐츠 길이: {len(content)}")
        
        try:
            # 지원 언어 및 문서 타입 확인
            if language not in self.supported_languages:
                print(f"🔍 지원하지 않는 언어: {language}")
                return {
                    "success": False,
                    "data": {"error": f"Unsupported language: {language}"}
                }
            
            if document_type not in self.supported_document_types:
                print(f"🔍 지원하지 않는 문서 타입: {document_type}")
                return {
                    "success": False,
                    "data": {"error": f"Unsupported document type: {document_type}"}
                }
            
            # 문서 파일 경로
            doc_path = self._get_document_path(language, document_type)
            print(f"🔍 업데이트할 파일 경로: {doc_path}")
            print(f"🔍 파일 존재 여부 (업데이트 전): {doc_path.exists()}")
            
            # 파일 저장
            try:
                print(f"🔍 파일 저장 시작...")
                doc_path.write_text(content, encoding='utf-8')
                print(f"🔍 파일 저장 성공!")
                print(f"🔍 파일 존재 여부 (업데이트 후): {doc_path.exists()}")
                print(f"🔍 파일 크기: {doc_path.stat().st_size} bytes")
                
                # 저장된 내용 확인
                saved_content = doc_path.read_text(encoding='utf-8')
                print(f"🔍 저장된 내용 길이: {len(saved_content)}")
                print(f"🔍 저장된 내용 미리보기: {saved_content[:100]}...")
                
                result = {
                    "success": True,
                    "data": {
                        "message": "문서가 성공적으로 업데이트되었습니다.",
                        "file_path": str(doc_path),
                        "content_length": len(content),
                        "saved_at": str(datetime.now())
                    }
                }
                
                print(f"🔍 업데이트 결과: {result}")
                return result
                
            except Exception as write_error:
                print(f"🔍 파일 저장 오류: {str(write_error)}")
                import traceback
                print(f"🔍 파일 저장 오류 상세: {traceback.format_exc()}")
                return {
                    "success": False,
                    "data": {"error": f"파일 저장 중 오류 발생: {str(write_error)}"}
                }
            
        except Exception as e:
            print(f"🔍 문서 업데이트 서비스 오류: {str(e)}")
            import traceback
            print(f"🔍 오류 상세: {traceback.format_exc()}")
            return {
                "success": False,
                "data": {"error": f"문서 업데이트 중 오류 발생: {str(e)}"}
            }
    
    async def list_documents(self, language: Optional[str] = None) -> Dict[str, Any]:
        """문서 목록 조회"""
        try:
            documents = []
            
            # 언어 필터링
            languages = [language] if language else self.supported_languages
            
            for lang in languages:
                if lang not in self.supported_languages:
                    continue
                
                lang_dir = self.documents_dir / lang
                if not lang_dir.exists():
                    continue
                
                for doc_type in self.supported_document_types:
                    doc_path = lang_dir / f"{doc_type}.md"
                    documents.append({
                        "language": lang,
                        "document_type": doc_type,
                        "exists": doc_path.exists(),
                        "path": str(doc_path),
                        "normalized_type": self._normalize_document_type(doc_type)
                    })
            
            return {
                "success": True,
                "data": {
                    "documents": documents,
                    "supported_languages": self.supported_languages,
                    "supported_document_types": self.supported_document_types,
                    "sidebar_mapping": self.sidebar_to_filename_mapping
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": {"error": str(e)}
            }

# 전역 인스턴스 생성
document_service = DocumentService() 