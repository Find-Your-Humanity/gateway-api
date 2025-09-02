import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """API 요청을 자동으로 로깅하는 미들웨어"""
    
    # 로깅에서 제외할 경로들
    EXCLUDED_PATHS = [
        "/health",           # 헬스체크
        "/metrics",          # 메트릭스
        "/favicon.ico",      # 파비콘
        "/robots.txt",       # 로봇 텍스트
        "/.well-known/",     # 웰노운 경로
        "/ping",             # 핑
        "/status"            # 상태
    ]
    
    async def dispatch(self, request: Request, call_next):
        # 요청 시작 시간 기록
        start_time = time.time()
        
        # 요청 정보 추출
        path = request.url.path
        method = request.method
        user_agent = request.headers.get("user-agent", "")
        
        # 제외할 경로 체크 - 로깅하지 않고 바로 응답
        if any(path.startswith(excluded_path) for excluded_path in self.EXCLUDED_PATHS):
            logger.debug(f"로깅 제외 경로: {path} - 헬스체크/모니터링용")
            response = await call_next(request)
            return response
        
        # 사용자 정보 추출 (인증된 경우)
        user_id = None
        api_key = None
        
        try:
            # 쿠키에서 사용자 정보 확인
            user = get_current_user_from_request(request)
            if user:
                user_id = user.get("id")
            
            # API 키 확인 (Authorization 헤더에서)
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]  # "Bearer " 제거
            elif auth_header.startswith("ApiKey "):
                api_key = auth_header[7:]  # "ApiKey " 제거
                
        except Exception as e:
            logger.warning(f"사용자 정보 추출 실패: {e}")
        
        # 다음 미들웨어/엔드포인트 실행
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # 예외 발생 시 500 에러로 처리
            status_code = 500
            logger.error(f"요청 처리 중 오류: {e}")
            raise
        
        # 응답 시간 계산 (밀리초)
        end_time = time.time()
        response_time = int((end_time - start_time) * 1000)
        
        # 로그 기록 (비동기로 처리하여 응답 지연 방지)
        try:
            await self._log_request_async(
                user_id=user_id,
                api_key=api_key,
                path=path,
                method=method,
                status_code=status_code,
                response_time=response_time,
                user_agent=user_agent
            )
        except Exception as e:
            logger.error(f"요청 로깅 실패: {e}")
        
        return response
    
    async def _log_request_async(self, user_id, api_key, path, method, status_code, response_time, user_agent):
        """비동기로 요청 로그를 데이터베이스에 저장"""
        import asyncio
        
        # 별도 스레드에서 동기 DB 작업 실행
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._log_request_sync, user_id, api_key, path, method, status_code, response_time, user_agent)
    
    def _log_request_sync(self, user_id, api_key, path, method, status_code, response_time, user_agent):
        """동기적으로 요청 로그를 데이터베이스에 저장"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 로그 데이터 삽입
                    insert_query = """
                        INSERT INTO request_logs 
                        (user_id, api_key, path, method, status_code, response_time, user_agent)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    cursor.execute(insert_query, (
                        user_id, api_key, path, method, status_code, 
                        response_time, user_agent
                    ))
                    conn.commit()
                    
        except Exception as e:
            logger.error(f"요청 로그 저장 실패: {e}")
            # 로그 저장 실패가 전체 요청에 영향을 주지 않도록 함
