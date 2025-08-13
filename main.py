from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes.auth import router as auth_router
from src.routes.dashboard import router as dashboard_router
import asyncio
from src.config.database import (
    init_database,
    test_connection,
    cleanup_password_reset_tokens,
    cleanup_password_reset_codes,
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