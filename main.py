from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.routes.auth import router as auth_router
from src.routes.dashboard import router as dashboard_router
import asyncio
from src.config.database import (
    init_database,
    test_connection,
    cleanup_password_reset_tokens,
    cleanup_password_reset_codes,
    aggregate_request_statistics,
    aggregate_error_stats_daily,
    aggregate_endpoint_usage_daily,
)

app = FastAPI(title="Real Captcha Gateway API", version="1.0.0")

# 인증 라우터 등록
app.include_router(auth_router)
app.include_router(dashboard_router)

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://realcatcha.com",
        "https://www.realcatcha.com",
        "https://test.realcatcha.com",
        "https://dashboard.realcatcha.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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
    print("🚀 Real Captcha Gateway API 시작 중...")
    
    # 데이터베이스 연결 테스트
    if test_connection():
        print("✅ 데이터베이스 연결 성공!")
        # 데이터베이스 초기화 (테이블 생성)
        try:
            init_database()
        except Exception as e:
            print(f"⚠️ 데이터베이스 초기화 실패: {e}")
        # 만료 토큰 정리 1회 수행 및 주기 실행
        try:
            deleted = cleanup_password_reset_tokens()
            if deleted:
                print(f"🧹 만료/사용 토큰 정리: {deleted}건 삭제")
            deleted_codes = cleanup_password_reset_codes()
            if deleted_codes:
                print(f"🧹 만료/사용 코드 정리: {deleted_codes}건 삭제")
        except Exception as e:
            print(f"⚠️ 토큰/코드 정리 실패: {e}")

        async def periodic_cleanup():
            while True:
                try:
                    deleted = cleanup_password_reset_tokens()
                    if deleted:
                        print(f"🧹(주기) 만료/사용 토큰 정리: {deleted}건 삭제")
                    deleted_codes = cleanup_password_reset_codes()
                    if deleted_codes:
                        print(f"🧹(주기) 만료/사용 코드 정리: {deleted_codes}건 삭제")
                    # 집계 작업 수행
                    a = aggregate_request_statistics(30)
                    e = aggregate_error_stats_daily(30)
                    p = aggregate_endpoint_usage_daily(30)
                    print(f"📈 집계 업데이트: stats={a}, error={e}, endpoint={p}")
                except Exception as e:
                    print(f"⚠️(주기) 토큰/코드 정리 실패: {e}")
                await asyncio.sleep(60 * 60 * 6)  # 6시간 간격

        asyncio.create_task(periodic_cleanup())
    else:
        print("❌ 데이터베이스 연결 실패!")

@app.get("/api/status")
def api_status():
    """API 상태 확인"""
    return {
        "service": "gateway-api",
        "status": "running",
        "database": "connected" if test_connection() else "disconnected"
    } 