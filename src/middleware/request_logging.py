import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.database import get_db_connection
from src.utils.auth import get_current_user_from_request

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """API 요청을 자동으로 로깅하는 미들웨어"""
    
    async def dispatch(self, request: Request, call_next):
        # 요청 시작 시간 기록
        start_time = time.time()
        
        # 요청 정보 추출
        path = request.url.path
        method = request.method
        user_agent = request.headers.get("user-agent", "")
        
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
    
    async def _log_request_async(self, **kwargs):
        """비동기로 요청 로그를 데이터베이스에 저장"""
        import asyncio
        
        # 별도 스레드에서 동기 DB 작업 실행
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._log_request_sync, **kwargs)
    
    def _log_request_sync(self, user_id, api_key, path, method, status_code, response_time, user_agent):
        """동기적으로 요청 로그를 데이터베이스에 저장"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # request_logs 테이블이 존재하는지 확인
                    cursor.execute("SHOW TABLES LIKE 'request_logs'")
                    table_exists = cursor.fetchone()
                    
                    if not table_exists:
                        # 테이블이 없으면 생성
                        create_table_query = """
                            CREATE TABLE request_logs (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                user_id INT NULL,
                                api_key VARCHAR(255) NULL,
                                path VARCHAR(500) NOT NULL,
                                method VARCHAR(10) NOT NULL,
                                status_code INT NOT NULL,
                                response_time INT NOT NULL,
                                user_agent TEXT NULL,
                                request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                INDEX idx_user_id (user_id),
                                INDEX idx_api_key (api_key),
                                INDEX idx_request_time (request_time),
                                INDEX idx_status_code (status_code),
                                INDEX idx_path (path),
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                        """
                        cursor.execute(create_table_query)
                        conn.commit()
                    
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
