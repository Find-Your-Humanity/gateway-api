import os
import json
from typing import Dict, Any, Optional
from pathlib import Path

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
            "faq", 
            "enterprise_account_management", 
            "recaptcha_migration", 
            "mobile_sdk", 
            "통합", 
            "pro_features", 
            "enterprise_overview"
        ]
        
        # 문서 저장소 초기화
        self._init_document_storage()
    
    def _init_document_storage(self):
        """문서 저장소 디렉토리 초기화"""
        for lang in self.supported_languages:
            lang_dir = self.documents_dir / lang
            lang_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_document_path(self, language: str, document_type: str) -> Path:
        """문서 파일 경로 반환"""
        return self.documents_dir / language / f"{document_type}.md"
    
    def _get_default_content(self, language: str, document_type: str) -> str:
        """기본 콘텐츠 반환"""
        if document_type == "developer_guide":
            if language == "ko":
                return """# RealCatcha 개발자 가이드

## 소개
RealCatcha는 기존 reCAPTCHA에서 전환하기 쉬운 차세대 캡차 솔루션입니다.

## 기본 원칙
1. 사용자 경험 우선
2. 보안성 보장
3. 쉬운 통합

## 설치 방법
```bash
npm install realcatcha
```

## 사용 방법
```javascript
import { RealCatcha } from 'realcatcha';

const captcha = new RealCatcha({
  siteKey: 'your-site-key'
});
```

## 다음 단계
더 자세한 정보는 API 문서를 참조하세요."""
            else:
                return """# RealCatcha Developer Guide

## Introduction
RealCatcha is a next-generation captcha solution that makes it easy to transition from reCAPTCHA.

## Basic Principles
1. User Experience First
2. Security Guaranteed
3. Easy Integration

## Installation
```bash
npm install realcatcha
```

## Usage
```javascript
import { RealCatcha } from 'realcatcha';

const captcha = new RealCatcha({
  siteKey: 'your-site-key'
});
```

## Next Steps
For more detailed information, please refer to the API documentation."""
        
        return f"# {document_type.replace('_', ' ').title()}\n\nThis is the default content for {document_type} in {language}."
    
    async def get_document(self, language: str, document_type: str) -> Dict[str, Any]:
        """문서 내용 조회"""
        try:
            # 지원 언어 및 문서 타입 확인
            if language not in self.supported_languages:
                return {
                    "success": False,
                    "data": {"error": f"Unsupported language: {language}"}
                }
            
            if document_type not in self.supported_document_types:
                return {
                    "success": False,
                    "data": {"error": f"Unsupported document type: {document_type}"}
                }
            
            # 문서 파일 경로
            doc_path = self._get_document_path(language, document_type)
            
            # 파일이 존재하면 읽기, 없으면 기본 콘텐츠 반환
            if doc_path.exists():
                content = doc_path.read_text(encoding='utf-8')
            else:
                content = self._get_default_content(language, document_type)
            
            return {
                "success": True,
                "data": {
                    "language": language,
                    "document_type": document_type,
                    "content": content,
                    "exists": doc_path.exists()
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": {"error": str(e)}
            }
    
    async def update_document(self, language: str, document_type: str, content: str) -> Dict[str, Any]:
        """문서 내용 업데이트"""
        try:
            # 지원 언어 및 문서 타입 확인
            if language not in self.supported_languages:
                return {
                    "success": False,
                    "data": {"error": f"Unsupported language: {language}"}
                }
            
            if document_type not in self.supported_document_types:
                return {
                    "success": False,
                    "data": {"error": f"Unsupported document type: {document_type}"}
                }
            
            # 문서 파일 경로
            doc_path = self._get_document_path(language, document_type)
            
            # 디렉토리 생성 (필요시)
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 파일에 내용 저장
            doc_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "data": {
                    "language": language,
                    "document_type": document_type,
                    "message": "Document updated successfully"
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": {"error": str(e)}
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
                        "path": str(doc_path)
                    })
            
            return {
                "success": True,
                "data": {
                    "documents": documents,
                    "supported_languages": self.supported_languages,
                    "supported_document_types": self.supported_document_types
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": {"error": str(e)}
            }

# 전역 인스턴스 생성
document_service = DocumentService() 