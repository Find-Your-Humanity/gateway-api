import os
import sys
import logging
import builtins

# 로깅 설정 및 사용 가이드 (gateway-api)
# ------------------------------------------------------------
# 1) 기본 동작
#    - 애플리케이션 시작 시 _setup_logging()이 표준 로깅을 초기화합니다.
#    - 환경변수 GATEWAY_API_LOG_LEVEL (기본: INFO)로 로그 레벨을 제어할 수 있습니다.
#      예) Windows PowerShell: $env:GATEWAY_API_LOG_LEVEL = "DEBUG"
#    - 로그 포맷: [YYYY-MM-DD HH:MM:SS] LEVEL logger.name: message
#    - uvicorn/fastapi 로거 레벨도 동일하게 맞춥니다.
#
# 2) print 리다이렉트
#    - _redirect_print_to_logging()이 builtins.print를 로거(app.print)로 연결합니다.
#    - 기존 코드의 print는 logger.info(표준출력), logger.error(표준에러)로 기록됩니다.
#    - 가능하면 신규 코드는 직접 logger = logging.getLogger(__name__) 후
#      logger.info()/warning()/error()/exception()을 사용하세요.
#
# 3) 레벨 선택 가이드
#    - 상세 진단/디버깅: logger.debug
#    - 일반 정보(정상 흐름): logger.info
#    - 주의/잠재적 문제: logger.warning
#    - 오류(처리 가능): logger.error
#    - 예외 스택과 함께 기록: logger.exception (except 블록 내부에서 사용)
#
# 4) 모듈별 권장 패턴
#    import logging
#    logger = logging.getLogger(__name__)
#    ...
#    logger.info("처리 완료")
# ------------------------------------------------------------
# Configure logging and redirect print to logging at import time

def _setup_logging():
    level_name = os.getenv("GATEWAY_API_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    # If no handlers are set (e.g., running under plain uvicorn can add its own), add one
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level)
    # Align common library loggers with our level
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(name).setLevel(level)


_setup_logging()

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.routes.auth import router as auth_router
from src.routes.dashboard import router as dashboard_router
from src.routes.admin import router as admin_router
from src.routes.billing import router as billing_router
from src.routes.api_keys import router as api_keys_router
from src.routes.captcha import router as captcha_router
from src.routes.admin_documents import router as admin_documents_router
from src.routes.payment_router import router as payment_router
from src.routes.user_stats import router as user_stats_router
from src.routes.admin_users import router as admin_users_router
from src.routes.suspicious_ips import router as suspicious_ips_router
from src.middleware.request_logging import RequestLoggingMiddleware
from src.middleware.usage_tracking import UsageTrackingMiddleware
from src.services.usage_service import usage_service
import asyncio
from datetime import datetime
from src.config.database import (
    init_database,
    test_connection,
    cleanup_password_reset_tokens,
    cleanup_password_reset_codes,
    cleanup_duplicate_request_statistics,
    aggregate_request_statistics,
    aggregate_error_stats_daily,
    aggregate_endpoint_usage_daily,
)

app = FastAPI(title="Real Captcha Gateway API", version="1.0.0")

# 라우터 등록
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(api_keys_router)
app.include_router(captcha_router)
app.include_router(admin_documents_router)
app.include_router(payment_router)
app.include_router(user_stats_router)
app.include_router(suspicious_ips_router)
app.include_router(admin_users_router)

# 미들웨어 등록 (순서 중요: CORS -> 로깅)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://realcatcha.com",
        "https://www.realcatcha.com",
        "https://test.realcatcha.com",
        "https://dashboard.realcatcha.com",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8081",  # 테스트용 추가
        "https://novelike-the-draw.static.hf.space",  # 임시 추가
        # Allow all localhost ports for development
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# 미들웨어 추가 (순서 중요: CORS -> 로깅 -> 사용량 추적)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(UsageTrackingMiddleware)

# 422 검증 오류를 사용자 친화적으로 반환하는 전역 핸들러
def _translate_validation_error(err: dict) -> dict:
    loc_parts = [str(x) for x in err.get("loc", []) if x != "body"]
    field = ".".join(loc_parts) if loc_parts else ""
    err_type = err.get("type", "")
    ctx = err.get("ctx") or {}
    msg = err.get("msg", "")

    if err_type.startswith("value_error.missing"):
        message = "필수 입력입니다."
    elif err_type == "type_error.email":
        message = "올바른 이메일 형식이 아닙니다."
    elif err_type == "value_error.any_str.min_length":
        limit = ctx.get("limit_value")
        message = f"최소 {limit}자 이상 입력해 주세요."
    else:
        message = msg
    return {"field": field, "message": message}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [_translate_validation_error(e) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})

@app.get("/")
def read_root():
    return {
        "message": "Real Captcha Gateway API", 
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 데이터베이스 연결 테스트"""
    logger.info("🚀 Real Captcha Gateway API 시작 중...")
    
    # 데이터베이스 연결 테스트
    if test_connection():
        logger.info("데이터베이스 연결 성공!")
        # 데이터베이스 초기화 (테이블 생성)
        try:
            init_database()
        except Exception as e:
            logger.exception(f"데이터베이스 초기화 실패: {e}")
        # 만료 토큰 정리 1회 수행 및 주기 실행
        try:
            deleted = cleanup_password_reset_tokens()
            if deleted:
                logger.info(f"만료/사용 토큰 정리: {deleted}건 삭제")
            deleted_codes = cleanup_password_reset_codes()
            if deleted_codes:
                logger.info(f"만료/사용 코드 정리: {deleted_codes}건 삭제")
        except Exception as e:
            logger.exception(f"토큰/코드 정리 실패: {e}")

        async def periodic_cleanup():
            while True:
                try:
                    deleted = cleanup_password_reset_tokens()
                    if deleted:
                        logger.info(f"(주기) 만료/사용 토큰 정리: {deleted}건 삭제")
                    deleted_codes = cleanup_password_reset_codes()
                    if deleted_codes:
                        logger.info(f"(주기) 만료/사용 코드 정리: {deleted_codes}건 삭제")
                    # 중복 데이터 정리 (매일 한 번만 실행)
                    if datetime.now().hour == 0 and datetime.now().minute < 5:  # 자정 이후 5분 내에만 실행
                        cleaned = cleanup_duplicate_request_statistics()
                        if cleaned > 0:
                            logger.info(f"🧹 중복 데이터 정리: {cleaned}건 삭제")
                    
                    # 집계 작업 수행
                    a = aggregate_request_statistics(30)
                    e = aggregate_error_stats_daily(30)
                    p = aggregate_endpoint_usage_daily(30)
                    logger.info(f"📈 집계 업데이트: stats={a}, error={e}, endpoint={p}")
                    
                    # 사용량 리셋 작업 수행 (매분, 매일, 매월)
                    reset_result = await usage_service.reset_periodic_usage()
                    if reset_result:
                        logger.info("🔄 사용량 리셋 완료")
                    
                except Exception as e:
                    logger.exception(f"⚠️(주기) 토큰/코드 정리 실패: {e}")
                await asyncio.sleep(60)  # 1분 간격으로 변경 (분당 리셋을 위해)

        asyncio.create_task(periodic_cleanup())
    else:
        logger.error("❌ 데이터베이스 연결 실패!")

@app.get("/api/status")
def api_status():
    """API 상태 확인"""
    return {
        "service": "gateway-api",
        "status": "running",
        "database": "connected" if test_connection() else "disconnected"
    } 