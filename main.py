from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes.auth import router as auth_router
from src.config.database import init_database, test_connection

app = FastAPI(title="Real Captcha Gateway API", version="1.0.0")

# 인증 라우터 등록
app.include_router(auth_router)

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",        # 개발환경 (React 개발 서버)
        "http://localhost:3001",        # 대시보드 개발 서버
        "https://realcatcha.com",       # 프로덕션 프론트엔드 도메인
        "https://www.realcatcha.com",   # www 서브도메인
        "https://test.realcatcha.com",  # 테스트 도메인
        "https://dashboard.realcatcha.com"  # 대시보드 도메인 
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