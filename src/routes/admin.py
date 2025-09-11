"""
관리자 전용 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Form, File, UploadFile
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from src.config.database import get_db_connection
from src.utils.auth import get_password_hash
from src.routes.auth import get_current_user_from_request
from src.utils.log_queries import (
    get_api_status_query,
    get_api_status_query_api_logs,
    get_response_time_query,
    get_error_rate_query,
    get_tps_query,
    get_system_summary_query,
    get_time_filter
)
from fastapi import Request
import logging
from datetime import datetime
import os
import httpx
import hmac, hashlib, base64, json, time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["admin"])
@router.get("/public", include_in_schema=False)
async def public_root_health():
    return {"ok": True}

@router.head("/public", include_in_schema=False)
async def public_root_health_head():
    from fastapi import Response
    return Response(status_code=200)

@router.post("/public/next-captcha")
async def public_next_captcha_proxy(request: Request):
    """
    공개 엔드포인트(데모용): 프론트는 공개키만 보내고, 게이트웨이가 데모 시크릿을 주입하여 captcha-api의 /api/next-captcha 로 포워딩.
    보안: 데모 공개키가 아닌 경우 거부.
    """
    demo_public_key = os.getenv("DEMO_PUBLIC_KEY", "rc_live_f49a055d62283fd02e8203ccaba70fc2")
    demo_secret_key = os.getenv("DEMO_SECRET_KEY")
    captcha_api_base = os.getenv("CAPTCHA_API_BASE", "http://captcha-api:8000")

    try:
        body = await request.json()
    except Exception:
        body = {}

    x_api_key = request.headers.get("x_api_key") or request.headers.get("x-api-key")
    if not x_api_key or x_api_key != demo_public_key:
        raise HTTPException(status_code=401, detail="Demo API key required")
    if not demo_secret_key:
        raise HTTPException(status_code=500, detail="Demo secret not configured")

    target_url = f"{captcha_api_base}/api/next-captcha"
    headers = {"x_api_key": x_api_key, "x_secret_key": demo_secret_key}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(target_url, json=body, headers=headers)
        return {"status": resp.status_code, **resp.json()}
    except httpx.HTTPError as e:
        logger.error(f"Proxy to captcha-api failed: {e}")
        raise HTTPException(status_code=502, detail="Captcha service unavailable")

# 위젯이 apiEndpoint + '/api/next-captcha' 형태로 호출하는 경우 대응용 별칭 경로
@router.post("/public/api/next-captcha", include_in_schema=False)
async def public_next_captcha_proxy_alias(request: Request):
    return await public_next_captcha_proxy(request)

# CORS 프리플라이트(OPTIONS) 및 HEAD 요청 허용
from fastapi import Response

@router.options("/public/next-captcha", include_in_schema=False)
async def public_next_captcha_options():
    return Response(status_code=200)

@router.head("/public/next-captcha", include_in_schema=False)
async def public_next_captcha_head():
    return Response(status_code=200)

@router.options("/public/api/next-captcha", include_in_schema=False)
async def public_next_captcha_alias_options():
    return Response(status_code=200)

@router.head("/public/api/next-captcha", include_in_schema=False)
async def public_next_captcha_alias_head():
    return Response(status_code=200)

# ===== Demo token endpoints (gateway-managed, no public/secret key on client) =====
def _sign_demo(payload: dict, secret: str) -> str:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(data).decode().rstrip('=') + "." + base64.urlsafe_b64encode(sig).decode().rstrip('=')

def _verify_demo(token: str, secret: str) -> dict:
    try:
        data_b64, sig_b64 = token.split(".", 1)
        # pad
        def _pad(s):
            return s + "=" * ((4 - len(s) % 4) % 4)
        data = base64.urlsafe_b64decode(_pad(data_b64))
        sig = base64.urlsafe_b64decode(_pad(sig_b64))
        exp_sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, exp_sig):
            return {}
        payload = json.loads(data.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return {}
        return payload
    except Exception:
        return {}

@router.post("/public/demo/token", include_in_schema=False)
async def demo_token_issue(request: Request):
    demo_secret = os.getenv("DEMO_TOKEN_SECRET")
    if not demo_secret:
        raise HTTPException(status_code=500, detail="Demo token not configured")
    allowed = os.getenv("DEMO_ALLOWED_ORIGINS", "*")
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if allowed != "*" and origin and not any(o for o in allowed.split(",") if o.strip() and o.strip() in origin):
        raise HTTPException(status_code=403, detail="Origin not allowed")
    ttl = int(os.getenv("DEMO_TOKEN_TTL", "300"))
    payload = {"iat": int(time.time()), "exp": int(time.time()) + ttl, "kind": "demo"}
    token = _sign_demo(payload, demo_secret)
    return {"success": True, "demo_token": token, "expires_in": ttl}

@router.post("/public/demo/next-captcha", include_in_schema=False)
async def demo_next_captcha(request: Request):
    demo_secret = os.getenv("DEMO_TOKEN_SECRET")
    if not demo_secret:
        raise HTTPException(status_code=500, detail="Demo token not configured")
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    demo_token = request.headers.get("x_demo_token") or request.headers.get("x-demo-token")
    if not demo_token:
        raise HTTPException(status_code=401, detail="Demo token required")
    payload = _verify_demo(demo_token, demo_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid demo token")
    # forward with demo keys
    demo_public_key = os.getenv("DEMO_PUBLIC_KEY", "rc_live_f49a055d62283fd02e8203ccaba70fc2")
    demo_secret_key = os.getenv("DEMO_SECRET_KEY")
    if not demo_secret_key:
        raise HTTPException(status_code=500, detail="Demo secret not configured")
    captcha_api_base = os.getenv("CAPTCHA_API_BASE", "http://captcha-api:8000")
    target_url = f"{captcha_api_base}/api/next-captcha"
    headers = {"x_api_key": demo_public_key, "x_secret_key": demo_secret_key}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(target_url, json=body, headers=headers)
        return {"status": resp.status_code, **resp.json()}
    except httpx.HTTPError as e:
        logger.error(f"Demo proxy to captcha-api failed: {e}")
        raise HTTPException(status_code=502, detail="Captcha service unavailable")

# wildcard HEAD/OPTIONS for /api/public/* to avoid 405
@router.options("/public/{path:path}", include_in_schema=False)
async def public_any_options(path: str):
    return Response(status_code=200)

@router.head("/public/{path:path}", include_in_schema=False)
async def public_any_head(path: str):
    return Response(status_code=200)

# Pydantic 모델들
class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    name: Optional[str] = None
    contact: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: str
    # 구독 정보 추가
    current_plan: Optional[str] = None
    plan_display_name: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_expires: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    name: Optional[str] = None
    contact: Optional[str] = None
    is_admin: bool = False
    plan_id: Optional[int] = None  # 초기 플랜 할당

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    name: Optional[str] = None
    contact: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class PlanResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    plan_type: str
    price: float
    currency: str
    billing_cycle: str
    monthly_request_limit: Optional[int] = None
    concurrent_requests: int
    features: Optional[dict] = None
    rate_limit_per_minute: int
    is_active: bool
    is_popular: bool
    sort_order: int
    # 통계 정보
    subscriber_count: Optional[int] = None

class PlanCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    plan_type: str = 'paid'
    price: float
    currency: str = 'KRW'
    billing_cycle: str = 'monthly'
    monthly_request_limit: Optional[int] = None
    concurrent_requests: int = 10
    features: Optional[dict] = None
    rate_limit_per_minute: int = 60
    is_active: bool = True
    is_popular: bool = False
    sort_order: int = 0

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    plan_type: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    billing_cycle: Optional[str] = None
    monthly_request_limit: Optional[int] = None
    concurrent_requests: Optional[int] = None
    features: Optional[dict] = None
    rate_limit_per_minute: Optional[int] = None
    is_active: Optional[bool] = None
    is_popular: Optional[bool] = None
    sort_order: Optional[int] = None

# 요청 상태 조회 관련 모델들
class RequestLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    api_key: Optional[str] = None
    path: str
    method: str
    status_code: int
    response_time: int
    user_agent: Optional[str] = None
    request_time: str
    # 추가 정보
    user_email: Optional[str] = None
    user_username: Optional[str] = None

class RequestStatsResponse(BaseModel):
    total_requests: int
    success_count: int
    failure_count: int
    avg_response_time: float
    unique_users: int
    unique_api_keys: int

class ErrorStatsResponse(BaseModel):
    status_code: int
    count: int
    percentage: float

class EndpointUsageResponse(BaseModel):
    endpoint: str
    requests: int
    avg_response_time: float
    percentage: float

class SubscriptionResponse(BaseModel):
    id: int
    user_id: int
    plan_id: int
    plan_name: str
    plan_display_name: str
    status: str
    amount: float
    currency: str
    payment_method: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    current_usage: int
    notes: Optional[str] = None

# 관리자 권한 확인 의존성
def require_admin(request: Request):
    """관리자 권한이 필요한 엔드포인트용 의존성"""
    try:
        user = get_current_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")
        
        if not (user.get('is_admin') == 1 or user.get('is_admin') == True):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        print(f"require_admin 오류: {e}")
        raise HTTPException(status_code=401, detail="인증 확인 중 오류가 발생했습니다.")

# ==================== 사용자 관리 API ====================

@router.get("/admin/test")
def test_admin_endpoint(request: Request):
    """관리자 API 테스트 엔드포인트"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 테이블 존재 확인
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                
                # users 테이블의 실제 구조 확인
                cursor.execute("DESCRIBE users")
                columns = cursor.fetchall()
                
                # 실제 데이터 개수 확인
                cursor.execute("SELECT COUNT(*) as user_count FROM users")
                result = cursor.fetchone()
                user_count = result['user_count'] if isinstance(result, dict) else result[0]
                
                # 샘플 데이터 몇 개 확인
                cursor.execute("SELECT id, email, username, name FROM users LIMIT 3")
                sample_users = cursor.fetchall()
                
                return {
                    "success": True, 
                    "message": "DB 연결 성공",
                    "tables": tables,
                    "user_table_columns": columns,
                    "total_users": user_count,
                    "sample_users": sample_users
                }
    except Exception as e:
        import traceback
        return {
            "success": False, 
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@router.get("/admin/users")
def get_users(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    """사용자 목록 조회 (권한 체크 제거하여 디버깅)"""
    try:
        print(f"Admin users API 호출됨 - page: {page}, limit: {limit}, search: {search}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 단순한 사용자 조회 (권한 체크 없이)
                print("DB 연결 성공")
                
                # 검색 조건 구성
                where_clause = ""
                params = []
                
                if search:
                    where_clause = "WHERE (email LIKE %s OR username LIKE %s OR name LIKE %s)"
                    search_param = f"%{search}%"
                    params = [search_param, search_param, search_param]
                
                # 총 개수 조회
                count_query = f"SELECT COUNT(*) as total_count FROM users {where_clause}"
                cursor.execute(count_query, params)
                result = cursor.fetchone()
                total = result['total_count'] if isinstance(result, dict) else result[0]
                print(f"총 사용자 수: {total}")
                
                # 페이지네이션된 데이터 조회 (현재 플랜 정보 포함) - 중복 방지
                offset = (page - 1) * limit
                data_query = f"""
                    SELECT DISTINCT
                        u.id, u.email, u.username, u.name, u.contact, 
                        u.is_active, u.is_admin, u.created_at,
                        p.name as current_plan,
                        p.name as plan_display_name,
                        COALESCE(
                            (SELECT us.status 
                             FROM user_subscriptions us 
                             WHERE us.user_id = u.id 
                             AND us.status = 'active' 
                             AND us.start_date <= CURDATE()
                             ORDER BY us.created_at DESC 
                             LIMIT 1), 
                            NULL
                        ) as subscription_status,
                        COALESCE(
                            (SELECT us.end_date 
                             FROM user_subscriptions us 
                             WHERE us.user_id = u.id 
                             AND us.status = 'active' 
                             AND us.start_date <= CURDATE()
                             ORDER BY us.created_at DESC 
                             LIMIT 1), 
                            NULL
                        ) as subscription_expires,
                        u.plan_id as user_plan_id
                    FROM users u
                    LEFT JOIN plans p ON u.plan_id = p.id
                    {where_clause}
                    ORDER BY u.created_at DESC
                    LIMIT %s OFFSET %s
                """
                data_params = params + [limit, offset]
                cursor.execute(data_query, data_params)
                users = cursor.fetchall()
                print(f"조회된 사용자 수: {len(users)}")
                
                result = {
                    "success": True,
                    "data": {
                        "data": users,
                        "pagination": {
                            "page": page,
                            "limit": limit,
                            "total": total,
                            "pages": (total + limit - 1) // limit if total > 0 else 1
                        }
                    }
                }
                print("응답 데이터 준비 완료")
                return result
                
    except Exception as e:
        print(f"사용자 목록 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "data": {
                "data": [],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": 0,
                    "pages": 1
                }
            }
        }

@router.post("/admin/users")
def create_user(
    user_data: UserCreate,
    request: Request,
    admin_user = Depends(require_admin)
):
    """새 사용자 생성"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 이메일/사용자명 중복 체크
                cursor.execute("SELECT id FROM users WHERE email = %s OR username = %s", 
                             (user_data.email, user_data.username))
                if cursor.fetchone():
                    raise HTTPException(status_code=400, detail="이미 존재하는 이메일 또는 사용자명입니다.")
                
                # 비밀번호 해시화
                password_hash = get_password_hash(user_data.password)
                
                # 사용자 생성
                cursor.execute("""
                    INSERT INTO users (email, username, password_hash, name, contact, is_admin)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_data.email, user_data.username, password_hash, 
                     user_data.name, user_data.contact, user_data.is_admin))
                
                user_id = cursor.lastrowid
                conn.commit()
                
                # 생성된 사용자 정보 반환
                cursor.execute("""
                    SELECT id, email, username, name, contact, is_active, is_admin, created_at 
                    FROM users WHERE id = %s
                """, (user_id,))
                user = cursor.fetchone()
                
                return {"success": True, "data": user}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 생성 실패: {e}")

@router.put("/admin/users/{user_id}")
def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    admin_user = Depends(require_admin)
):
    """사용자 정보 수정"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자 존재 확인
                cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
                
                # 업데이트할 필드 구성
                update_fields = []
                params = []
                
                for field, value in user_data.dict(exclude_unset=True).items():
                    if value is not None:
                        update_fields.append(f"{field} = %s")
                        params.append(value)
                
                if not update_fields:
                    raise HTTPException(status_code=400, detail="업데이트할 데이터가 없습니다.")
                
                params.append(user_id)
                query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, params)
                conn.commit()
                
                # 수정된 사용자 정보 반환
                cursor.execute("""
                    SELECT id, email, username, name, contact, is_active, is_admin, created_at 
                    FROM users WHERE id = %s
                """, (user_id,))
                user = cursor.fetchone()
                
                return {"success": True, "data": user}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 수정 실패: {e}")

@router.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin_user = Depends(require_admin)
):
    """사용자 삭제 (비활성화)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 자기 자신은 삭제할 수 없음
                if admin_user['id'] == user_id:
                    raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다.")
                
                # 사용자 존재 확인
                cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
                
                # 비활성화 (실제 삭제 대신)
                cursor.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (user_id,))
                conn.commit()
                
                return {"success": True, "message": "사용자가 비활성화되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 삭제 실패: {e}")

# ==================== 요금제 관리 API ====================

@router.get("/admin/plans")
def get_plans(
    request: Request,
    admin_user = Depends(require_admin)
):
    """요금제 목록 조회 (구독자 수 포함)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 구독자 수 집계 기준을 통일: users.plan_id + 활성 계정 기준
                # 추가 지표: active_subscribers (user_subscriptions.status='active')
                query = """
                    SELECT 
                        p.id, p.name, p.display_name, p.description, p.plan_type,
                        p.price, p.currency, p.billing_cycle,
                        p.monthly_request_limit, p.concurrent_requests,
                        p.features, p.rate_limit_per_minute,
                        p.is_active, p.is_popular, p.sort_order,
                        p.created_at, p.updated_at,
                        /* 현재 활성 사용자 기준 구독자 수 (중복 제거) */
                        (
                            SELECT COUNT(DISTINCT u.id) 
                            FROM users u 
                            WHERE u.plan_id = p.id AND (u.is_active = 1 OR u.is_active = TRUE)
                        ) AS subscriber_count,
                        /* 활성 구독(결제 관점) 수 (중복 제거) */
                        (
                            SELECT COUNT(DISTINCT us.user_id) 
                            FROM user_subscriptions us 
                            WHERE us.plan_id = p.id AND us.status = 'active'
                        ) AS active_subscribers
                    FROM plans p
                    ORDER BY p.sort_order, p.id
                """
                cursor.execute(query)
                plans = cursor.fetchall()
                return {"success": True, "data": plans}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 목록 조회 실패: {e}")

@router.post("/admin/plans")
def create_plan(
    plan_data: PlanCreate,
    request: Request,
    admin_user = Depends(require_admin)
):
    """새 요금제 생성"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO plans (name, price, request_limit, description)
                    VALUES (%s, %s, %s, %s)
                """, (plan_data.name, plan_data.price, plan_data.request_limit, plan_data.description))
                
                plan_id = cursor.lastrowid
                conn.commit()
                
                # 생성된 요금제 정보 반환
                cursor.execute("SELECT id, name, price, request_limit, description FROM plans WHERE id = %s", (plan_id,))
                plan = cursor.fetchone()
                
                return {"success": True, "data": plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 생성 실패: {e}")

@router.put("/admin/plans/{plan_id}")
def update_plan(
    plan_id: int,
    plan_data: PlanUpdate,
    request: Request,
    admin_user = Depends(require_admin)
):
    """요금제 수정"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 요금제 존재 확인
                cursor.execute("SELECT id FROM plans WHERE id = %s", (plan_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다.")
                
                # 업데이트할 필드 구성
                update_fields = []
                params = []
                
                for field, value in plan_data.dict(exclude_unset=True).items():
                    if value is not None:
                        update_fields.append(f"{field} = %s")
                        params.append(value)
                
                if not update_fields:
                    raise HTTPException(status_code=400, detail="업데이트할 데이터가 없습니다.")
                
                params.append(plan_id)
                query = f"UPDATE plans SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, params)
                conn.commit()
                
                # 수정된 요금제 정보 반환
                cursor.execute("SELECT id, name, price, request_limit, description FROM plans WHERE id = %s", (plan_id,))
                plan = cursor.fetchone()
                
                return {"success": True, "data": plan}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 수정 실패: {e}")

@router.delete("/admin/plans/{plan_id}")
def delete_plan(
    plan_id: int,
    request: Request,
    admin_user = Depends(require_admin)
):
    """요금제 삭제"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 요금제 존재 확인
                cursor.execute("SELECT id FROM plans WHERE id = %s", (plan_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다.")
                
                # 현재 사용 중인 구독이 있는지 확인
                cursor.execute("SELECT COUNT(*) FROM user_subscriptions WHERE plan_id = %s", (plan_id,))
                subscription_count = cursor.fetchone()[0]
                
                if subscription_count > 0:
                    raise HTTPException(status_code=400, detail=f"현재 {subscription_count}명의 사용자가 이 요금제를 사용 중입니다.")
                
                # 요금제 삭제
                cursor.execute("DELETE FROM plans WHERE id = %s", (plan_id,))
                conn.commit()
                
                return {"success": True, "message": "요금제가 삭제되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 삭제 실패: {e}")

# ==================== 사용자 구독 관리 API ====================

@router.get("/admin/subscriptions")
def get_subscriptions(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    admin_user = Depends(require_admin)
):
    """전체 구독 목록 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                where_clause = "WHERE 1=1"
                params = []
                
                if status:
                    where_clause += " AND us.status = %s"
                    params.append(status)
                
                # 총 개수 조회
                count_query = f"""
                    SELECT COUNT(*) as total_count 
                    FROM user_subscriptions us
                    JOIN users u ON us.user_id = u.id
                    JOIN plans p ON us.plan_id = p.id
                    {where_clause}
                """
                cursor.execute(count_query, params)
                result = cursor.fetchone()
                total = result['total_count'] if isinstance(result, dict) else result[0]
                
                # 페이지네이션된 데이터 조회
                offset = (page - 1) * limit
                query = f"""
                    SELECT 
                        us.id, us.user_id, us.plan_id, us.status, us.amount, us.currency,
                        us.payment_method, us.start_date, us.end_date, us.current_usage, us.notes,
                        u.username, u.email,
                        p.name as plan_name, p.display_name as plan_display_name
                    FROM user_subscriptions us
                    JOIN users u ON us.user_id = u.id
                    JOIN plans p ON us.plan_id = p.id
                    {where_clause}
                    ORDER BY us.created_at DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, offset])
                cursor.execute(query, params)
                subscriptions = cursor.fetchall()
                
                return {
                    "success": True,
                    "data": {
                        "data": subscriptions,
                        "pagination": {
                            "page": page,
                            "limit": limit,
                            "total": total,
                            "pages": (total + limit - 1) // limit if total > 0 else 1
                        }
                    }
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"구독 목록 조회 실패: {e}")

@router.get("/admin/users/{user_id}/subscription")
def get_user_subscription(
    user_id: int,
    request: Request,
    admin_user = Depends(require_admin)
):
    """사용자의 현재 구독 정보 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT 
                        us.id, us.user_id, us.plan_id, us.status, us.amount, us.currency,
                        us.payment_method, us.start_date, us.end_date, us.current_usage, us.notes,
                        p.name as plan_name, p.display_name as plan_display_name,
                        p.monthly_request_limit, p.price
                    FROM user_subscriptions us
                    JOIN plans p ON us.plan_id = p.id
                    WHERE us.user_id = %s AND us.status = 'active'
                    ORDER BY us.start_date DESC
                    LIMIT 1
                """
                cursor.execute(query, (user_id,))
                subscription = cursor.fetchone()
                
                if not subscription:
                    return {"success": True, "data": None, "message": "활성 구독이 없습니다."}
                
                return {"success": True, "data": subscription}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"구독 정보 조회 실패: {e}")

@router.post("/admin/users/{user_id}/subscription")
def assign_plan_to_user(
    user_id: int,
    request: Request,
    plan_id: int = Query(..., description="할당할 플랜 ID"),
    admin_user = Depends(require_admin)
):
    """사용자에게 요금제 할당"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자와 요금제 존재 확인
                cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
                
                cursor.execute("SELECT id, price FROM plans WHERE id = %s", (plan_id,))
                plan = cursor.fetchone()
                if not plan:
                    raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다.")
                
                # 기존 활성 구독 종료
                cursor.execute("""
                    UPDATE user_subscriptions 
                    SET status = 'cancelled', end_date = CURDATE() 
                    WHERE user_id = %s AND status = 'active'
                """, (user_id,))
                
                # 새 구독 생성
                plan_price = plan['price'] if isinstance(plan, dict) else plan[1]
                cursor.execute("""
                    INSERT INTO user_subscriptions (
                        user_id, plan_id, start_date, status, amount, 
                        payment_method, notes
                    )
                    VALUES (%s, %s, CURDATE(), 'active', %s, 'manual', '관리자가 할당한 플랜')
                """, (user_id, plan_id, plan_price))
                
                conn.commit()
                
                return {"success": True, "message": "요금제가 할당되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 할당 실패: {e}")

@router.put("/admin/subscriptions/{subscription_id}")
def update_subscription(
    subscription_id: int,
    request: Request,
    status: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    admin_user = Depends(require_admin)
):
    """구독 정보 수정"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 구독 존재 확인
                cursor.execute("SELECT id FROM user_subscriptions WHERE id = %s", (subscription_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="구독을 찾을 수 없습니다.")
                
                # 업데이트할 필드 구성
                update_fields = []
                params = []
                
                if status:
                    update_fields.append("status = %s")
                    params.append(status)
                
                if end_date:
                    update_fields.append("end_date = %s")
                    params.append(end_date)
                
                if notes is not None:
                    update_fields.append("notes = %s")
                    params.append(notes)
                
                if not update_fields:
                    raise HTTPException(status_code=400, detail="업데이트할 데이터가 없습니다.")
                
                params.append(subscription_id)
                query = f"UPDATE user_subscriptions SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, params)
                conn.commit()
                
                return {"success": True, "message": "구독 정보가 수정되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"구독 수정 실패: {e}")

# ==================== 요금제별 구독자 상세 정보 API ====================

@router.get("/admin/plans/{plan_id}/subscribers")
def get_plan_subscribers(
    plan_id: int,
    request: Request,
    admin_user = Depends(require_admin)
):
    """특정 요금제의 구독자 상세 정보 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 먼저 플랜이 존재하는지 확인
                cursor.execute("SELECT id, name, display_name FROM plans WHERE id = %s", (plan_id,))
                plan = cursor.fetchone()
                if not plan:
                    raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다")
                
                # 단순한 구독자 정보만 조회 (문제 발생 소지 최소화)
                query = """
                    SELECT 
                        u.id as user_id,
                        u.username,
                        u.email,
                        COALESCE(u.name, '') as name,
                        u.created_at as user_created_at,
                        us.id as subscription_id,
                        us.start_date,
                        us.end_date,
                        COALESCE(us.status, 'active') as subscription_status,
                        us.created_at as subscription_created_at,
                        p.name as plan_name,
                        p.display_name as plan_display_name,
                        COALESCE(p.monthly_request_limit, 0) as monthly_request_limit
                    FROM user_subscriptions us
                    JOIN users u ON us.user_id = u.id
                    JOIN plans p ON us.plan_id = p.id
                    WHERE us.plan_id = %s 
                    ORDER BY us.created_at DESC
                """
                
                cursor.execute(query, (plan_id,))
                result = cursor.fetchall()
                
                # 결과를 딕셔너리 형태로 변환
                subscribers = []
                for row in result:
                    if isinstance(row, tuple):
                        subscriber = {
                            "user_id": row[0],
                            "username": row[1],
                            "email": row[2],
                            "name": row[3],
                            "user_created_at": str(row[4]) if row[4] else "",
                            "subscription_id": row[5],
                            "start_date": str(row[6]) if row[6] else "",
                            "end_date": str(row[7]) if row[7] else "",
                            "subscription_status": row[8],
                            "subscription_created_at": str(row[9]) if row[9] else "",
                            "plan_name": row[10],
                            "plan_display_name": row[11],
                            "monthly_request_limit": row[12],
                            "amount": 0,
                            "payment_method": "manual",
                            "notes": "",
                            "monthly_requests_used": 0,
                            "daily_requests_used": 0,
                            "last_request_time": None
                        }
                    else:
                        # 딕셔너리 형태의 경우
                        subscriber = dict(row)
                        subscriber.update({
                            "amount": 0,
                            "payment_method": "manual",
                            "notes": "",
                            "monthly_requests_used": 0,
                            "daily_requests_used": 0,
                            "last_request_time": None
                        })
                    subscribers.append(subscriber)
                
                # 플랜 통계 요약
                plan_info = {
                    "id": plan[0] if isinstance(plan, tuple) else plan["id"],
                    "name": plan[1] if isinstance(plan, tuple) else plan["name"],
                    "display_name": plan[2] if isinstance(plan, tuple) else plan["display_name"]
                }
                
                active_count = sum(1 for s in subscribers if s["subscription_status"] == "active")
                
                plan_stats = {
                    "plan_info": plan_info,
                    "total_subscribers": len(subscribers),
                    "active_subscribers": active_count,
                    "total_monthly_requests": 0,
                    "total_daily_requests": 0
                }
                
                return {
                    "success": True,
                    "data": {
                        "plan_stats": plan_stats,
                        "subscribers": subscribers
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error fetching plan subscribers: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"구독자 정보 조회 실패: {str(e)}")

# ==================== 문의사항 관리 API ====================

@router.post("/contact")
def submit_contact_request(
    request: Request,
    subject: str = Form(...),
    contact: str = Form(...),
    email: str = Form(...),  # 폼에서 받지만 무시하고 쿠키에서 사용자 이메일 사용
    message: str = Form(...),
    file: Optional[UploadFile] = File(None)
):
    """고객 문의 제출 (로그인 사용자만)"""
    try:
        # 로그인 체크
        user = get_current_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        
        # 쿠키에서 사용자 정보 강제 사용 (폼의 email 무시)
        user_email = user["email"]
        user_id = user["id"]
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 테이블이 존재하는지 확인하고 없으면 생성
                cursor.execute("SHOW TABLES LIKE 'contact_requests'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    # 테이블 생성 (user_id 컬럼 추가)
                    create_table_query = """
                        CREATE TABLE contact_requests (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            subject VARCHAR(255) NOT NULL,
                            contact VARCHAR(100) NOT NULL,
                            email VARCHAR(255) NOT NULL,
                            user_id INT NULL,
                            message TEXT NOT NULL,
                            attachment_filename VARCHAR(255) NULL,
                            attachment_data LONGBLOB NULL,
                            status ENUM('unread', 'in_progress', 'resolved') DEFAULT 'unread',
                            admin_response TEXT NULL,
                            admin_id INT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            resolved_at TIMESTAMP NULL,
                            INDEX idx_status (status),
                            INDEX idx_created_at (created_at),
                            INDEX idx_email (email),
                            INDEX idx_user_id (user_id),
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                    cursor.execute(create_table_query)
                    conn.commit()
                else:
                    # 기존 테이블에 user_id 컬럼이 있는지 확인
                    cursor.execute("SHOW COLUMNS FROM contact_requests LIKE 'user_id'")
                    user_id_exists = cursor.fetchone()
                    
                    if not user_id_exists:
                        # user_id 컬럼 추가
                        cursor.execute("ALTER TABLE contact_requests ADD COLUMN user_id INT NULL, ADD INDEX idx_user_id(user_id)")
                        conn.commit()
                
                # 첨부파일 처리
                attachment_filename = None
                attachment_data = None
                
                if file and file.filename:
                    attachment_filename = file.filename
                    attachment_data = file.file.read()
                
                # 문의 저장 (user_id 포함)
                query = """
                    INSERT INTO contact_requests 
                    (subject, contact, email, user_id, message, attachment_filename, attachment_data, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'unread')
                """
                
                cursor.execute(query, (
                    subject, contact, user_email, user_id, message, 
                    attachment_filename, attachment_data
                ))
                
                # 생성된 문의 ID 가져오기
                contact_id = cursor.lastrowid
                conn.commit()
                
                return {
                    "success": True, 
                    "message": "문의가 성공적으로 접수되었습니다.",
                    "contact_id": contact_id,
                    "status_check_url": f"https://www.realcatcha.com/contact-status?email={user_email}&id={contact_id}"
                }
                
    except HTTPException:
        # HTTPException은 그대로 전달
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error submitting contact request: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"문의 제출 실패: {str(e)}")

@router.get("/admin/contact-requests")
def get_contact_requests(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    admin_user = Depends(require_admin)
):
    """관리자용 문의사항 목록 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 먼저 테이블이 존재하는지 확인
                cursor.execute("SHOW TABLES LIKE 'contact_requests'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    # 테이블이 없으면 빈 결과 반환
                    return {
                        "success": True,
                        "data": {
                            "data": [],
                            "pagination": {
                                "page": page,
                                "limit": limit,
                                "total": 0,
                                "pages": 1
                            }
                        }
                    }
                
                # 필터 조건 구성
                where_conditions = []
                params = []
                
                if status:
                    where_conditions.append("cr.status = %s")
                    params.append(status)
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                # 총 개수 조회
                count_query = f"""
                    SELECT COUNT(*) as total_count 
                    FROM contact_requests cr
                    {where_clause}
                """
                cursor.execute(count_query, params)
                result = cursor.fetchone()
                total = result[0] if isinstance(result, tuple) else result["total_count"]
                
                # 목록 조회
                offset = (page - 1) * limit
                query = f"""
                    SELECT 
                        cr.id,
                        cr.subject,
                        cr.contact,
                        cr.email,
                        cr.message,
                        COALESCE(cr.attachment_filename, '') as attachment_filename,
                        COALESCE(cr.status, 'unread') as status,
                        COALESCE(cr.admin_response, '') as admin_response,
                        cr.created_at,
                        cr.updated_at,
                        cr.resolved_at,
                        COALESCE(u.username, '') as admin_username
                    FROM contact_requests cr
                    LEFT JOIN users u ON cr.admin_id = u.id
                    {where_clause}
                    ORDER BY cr.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                params.extend([limit, offset])
                cursor.execute(query, params)
                contacts = cursor.fetchall()
                
                # 결과를 딕셔너리 형태로 변환
                contact_list = []
                for row in contacts:
                    if isinstance(row, tuple):
                        contact_item = {
                            "id": row[0],
                            "subject": row[1],
                            "contact": row[2],
                            "email": row[3],
                            "message": row[4],
                            "attachment_filename": row[5],
                            "status": row[6],
                            "admin_response": row[7],
                            "created_at": str(row[8]) if row[8] else "",
                            "updated_at": str(row[9]) if row[9] else "",
                            "resolved_at": str(row[10]) if row[10] else "",
                            "admin_username": row[11]
                        }
                    else:
                        contact_item = dict(row)
                    contact_list.append(contact_item)
                
                return {
                    "success": True,
                    "data": {
                        "data": contact_list,
                        "pagination": {
                            "page": page,
                            "limit": limit,
                            "total": total,
                            "pages": (total + limit - 1) // limit if total > 0 else 1
                        }
                    }
                }
                
    except Exception as e:
        import traceback
        logger.error(f"Error fetching contact requests: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"문의사항 조회 실패: {str(e)}")

@router.put("/admin/contact-requests/{contact_id}")
def update_contact_request(
    contact_id: int,
    request: Request,
    status: Optional[str] = Query(None),
    admin_response: Optional[str] = Query(None),
    admin_user = Depends(require_admin)
):
    """관리자용 문의사항 상태 업데이트"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 테이블 존재 확인
                cursor.execute("SHOW TABLES LIKE 'contact_requests'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    raise HTTPException(status_code=404, detail="문의 시스템이 아직 초기화되지 않았습니다.")
                
                # 문의사항 존재 확인
                cursor.execute("SELECT id FROM contact_requests WHERE id = %s", (contact_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="문의사항을 찾을 수 없습니다.")
                
                # 업데이트할 필드 구성
                update_fields = []
                params = []
                
                if status:
                    update_fields.append("status = %s")
                    params.append(status)
                    
                    # resolved 상태일 때 해결 시간 기록
                    if status == "resolved":
                        update_fields.append("resolved_at = NOW()")
                
                if admin_response is not None:
                    update_fields.append("admin_response = %s")
                    params.append(admin_response)
                
                # 처리한 관리자 기록
                if admin_user and "id" in admin_user:
                    update_fields.append("admin_id = %s")
                    params.append(admin_user["id"])
                
                if not update_fields:
                    raise HTTPException(status_code=400, detail="업데이트할 데이터가 없습니다.")
                
                params.append(contact_id)
                query = f"UPDATE contact_requests SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, params)
                conn.commit()
                
                return {"success": True, "message": "문의사항이 업데이트되었습니다."}
                
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error updating contact request: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"문의사항 업데이트 실패: {str(e)}")

@router.get("/admin/contact-requests/{contact_id}/attachment")
def download_contact_attachment(
    contact_id: int,
    request: Request,
    admin_user = Depends(require_admin)
):
    """첨부파일 다운로드"""
    try:
        logger.info(f"Attempting to download attachment for contact_id: {contact_id}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 테이블 존재 확인
                cursor.execute("SHOW TABLES LIKE 'contact_requests'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    logger.error("contact_requests table does not exist")
                    raise HTTPException(status_code=404, detail="문의 시스템이 아직 초기화되지 않았습니다.")
                
                cursor.execute(
                    "SELECT attachment_filename, attachment_data FROM contact_requests WHERE id = %s",
                    (contact_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    logger.error(f"No contact request found with id: {contact_id}")
                    raise HTTPException(status_code=404, detail="문의사항을 찾을 수 없습니다.")
                
                filename = result[0] if isinstance(result, tuple) else result.get("attachment_filename")
                file_data = result[1] if isinstance(result, tuple) else result.get("attachment_data")
                
                logger.info(f"Found attachment: filename={filename}, data_type={type(file_data)}, data_size={len(file_data) if file_data else 0}")
                
                if not filename or not file_data:
                    logger.error(f"Missing attachment data: filename={filename}, has_data={bool(file_data)}")
                    raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다.")
                
                # 파일 데이터 타입 확인 및 변환
                if isinstance(file_data, str):
                    # 문자열인 경우 바이너리로 변환
                    file_data = file_data.encode('utf-8')
                elif not isinstance(file_data, bytes):
                    # 기타 타입인 경우 바이트로 변환 시도
                    try:
                        file_data = bytes(file_data)
                    except Exception as e:
                        logger.error(f"Failed to convert file data to bytes: {e}")
                        raise HTTPException(status_code=500, detail="파일 데이터 변환 실패")
                
                from fastapi.responses import Response
                import mimetypes
                import urllib.parse
                
                # 안전한 파일명 처리
                safe_filename = filename.replace('"', '')
                
                # MIME 타입 결정
                content_type = mimetypes.guess_type(safe_filename)[0] or 'application/octet-stream'
                
                # 파일명 인코딩 (한글 지원)
                try:
                    encoded_filename = urllib.parse.quote(safe_filename.encode('utf-8'))
                except Exception:
                    encoded_filename = urllib.parse.quote(safe_filename)
                
                headers = {
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                    "Content-Type": content_type,
                    "Content-Length": str(len(file_data)),
                    "Cache-Control": "no-cache"
                }
                
                return Response(
                    content=file_data,
                    media_type=content_type,
                    headers=headers
                )
                
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error downloading attachment: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"첨부파일 다운로드 실패: {str(e)}")

# 테스트용 간단한 다운로드 API
@router.get("/admin/test-download/{contact_id}")
def test_download_attachment(
    contact_id: int,
    request: Request,
    admin_user = Depends(require_admin)
):
    """테스트용 첨부파일 다운로드"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 간단한 정보만 조회
                cursor.execute(
                    "SELECT attachment_filename, LENGTH(attachment_data) as data_length FROM contact_requests WHERE id = %s",
                    (contact_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    return {"error": "문의사항을 찾을 수 없습니다."}
                
                filename = result[0] if isinstance(result, tuple) else result.get("attachment_filename")
                data_length = result[1] if isinstance(result, tuple) else result.get("data_length")
                
                return {
                    "success": True,
                    "filename": filename,
                    "data_length": data_length,
                    "has_attachment": bool(filename and data_length)
                }
                
    except Exception as e:
        return {"error": f"조회 실패: {str(e)}"}

# ==================== 사용자용 문의 조회 API ====================

@router.get("/contact-status")
def get_contact_status(
    request: Request,
    email: str = Query(..., description="문의 시 입력한 이메일"),
    contact_id: Optional[int] = Query(None, description="문의 ID (선택사항)")
):
    """사용자용 문의 상태 조회 (이메일 기반)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 테이블 존재 확인
                cursor.execute("SHOW TABLES LIKE 'contact_requests'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    return {
                        "success": True,
                        "data": []
                    }
                
                # 이메일 기반으로 문의 조회
                where_conditions = ["email = %s"]
                params = [email]
                
                if contact_id:
                    where_conditions.append("id = %s")
                    params.append(contact_id)
                
                where_clause = " AND ".join(where_conditions)
                
                query = f"""
                    SELECT 
                        id,
                        subject,
                        message,
                        status,
                        admin_response,
                        created_at,
                        updated_at,
                        resolved_at
                    FROM contact_requests 
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                """
                
                cursor.execute(query, params)
                contacts = cursor.fetchall()
                
                # 결과를 딕셔너리 형태로 변환
                contact_list = []
                for row in contacts:
                    if isinstance(row, tuple):
                        contact_item = {
                            "id": row[0],
                            "subject": row[1],
                            "message": row[2],
                            "status": row[3],
                            "admin_response": row[4],
                            "created_at": str(row[5]) if row[5] else "",
                            "updated_at": str(row[6]) if row[6] else "",
                            "resolved_at": str(row[7]) if row[7] else "",
                            "status_display": {
                                "unread": "접수됨",
                                "in_progress": "처리 중",
                                "resolved": "해결됨"
                            }.get(row[3], row[3])
                        }
                    else:
                        contact_item = dict(row)
                        contact_item["status_display"] = {
                            "unread": "접수됨",
                            "in_progress": "처리 중", 
                            "resolved": "해결됨"
                        }.get(contact_item["status"], contact_item["status"])
                    
                    contact_list.append(contact_item)
                
                return {
                    "success": True,
                    "data": contact_list
                }
                
    except Exception as e:
        import traceback
        logger.error(f"Error fetching contact status: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"문의 상태 조회 실패: {str(e)}")


@router.get("/my-contact-requests")
async def get_my_contact_requests(request: Request):
    """
    현재 로그인한 사용자의 문의사항 목록 조회
    """
    import traceback
    
    try:
        # 사용자 인증 확인
        current_user = get_current_user_from_request(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다")
        
        user_email = current_user.get("email")
        if not user_email:
            raise HTTPException(status_code=400, detail="사용자 이메일 정보가 없습니다")
        
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # contact_requests 테이블 존재 확인
                cursor.execute("SHOW TABLES LIKE 'contact_requests'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    logger.info("contact_requests table does not exist, returning empty list")
                    return {
                        "success": True,
                        "contact_requests": []
                    }
                
                # 사용자의 문의사항 조회
                query = """
                    SELECT 
                        id,
                        subject,
                        contact,
                        email,
                        message,
                        attachment_filename,
                        status,
                        admin_response,
                        admin_id,
                        created_at,
                        updated_at,
                        resolved_at
                    FROM contact_requests 
                    WHERE email = %s
                    ORDER BY created_at DESC
                """
                
                cursor.execute(query, (user_email,))
                contacts = cursor.fetchall()
                
                # 결과를 리스트 형태로 변환 (튜플 기반)
                contact_list = []
                for row in contacts:
                    if isinstance(row, tuple):
                        contact_item = {
                            "id": row[0],
                            "subject": row[1] or "",
                            "contact": row[2] or "",
                            "email": row[3] or "",
                            "message": row[4] or "",
                            "attachment_filename": row[5],
                            "status": row[6] or "unread",
                            "admin_response": row[7],
                            "admin_id": row[8],
                            "created_at": str(row[9]) if row[9] else "",
                            "updated_at": str(row[10]) if row[10] else "",
                            "resolved_at": str(row[11]) if row[11] else ""
                        }
                    else:
                        # 딕셔너리 형태인 경우 (일부 환경에서)
                        contact_item = {
                            "id": row["id"],
                            "subject": row["subject"] or "",
                            "contact": row["contact"] or "",
                            "email": row["email"] or "",
                            "message": row["message"] or "",
                            "attachment_filename": row["attachment_filename"],
                            "status": row["status"] or "unread",
                            "admin_response": row["admin_response"],
                            "admin_id": row["admin_id"],
                            "created_at": str(row["created_at"]) if row["created_at"] else "",
                            "updated_at": str(row["updated_at"]) if row["updated_at"] else "",
                            "resolved_at": str(row["resolved_at"]) if row["resolved_at"] else ""
                        }
                    contact_list.append(contact_item)
                
                logger.info(f"Found {len(contact_list)} contact requests for user {user_email}")
                
                return {
                    "success": True,
                    "contact_requests": contact_list
                }
                
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error fetching user contact requests: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"문의사항 조회 실패: {str(e)}")

# ===== 요청 상태 관리 API =====

@router.get("/admin/request-stats")
def get_request_statistics(
    request: Request,
    days: int = Query(7, description="조회할 일수", ge=1, le=90)
):
    """요청 통계 조회"""
    try:
        # 관리자 권한 확인
        current_user = get_current_user_from_request(request)
        if not current_user or not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 전체 통계
                stats_query = f"""
                    SELECT 
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) as success_count,
                        SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as failure_count,
                        AVG(response_time) as avg_response_time,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(DISTINCT api_key) as unique_api_keys
                    FROM (
                        SELECT status_code, response_time, user_id, api_key FROM request_logs
                        WHERE request_time >= NOW() - INTERVAL {days} DAY
                        UNION ALL
                        SELECT status_code, response_time, user_id, api_key FROM api_request_logs
                        WHERE created_at >= NOW() - INTERVAL {days} DAY
                    ) as combined_logs
                """
                cursor.execute(stats_query)
                stats = cursor.fetchone()
                
                if not stats:
                    return {
                        "total_requests": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "avg_response_time": 0,
                        "unique_users": 0,
                        "unique_api_keys": 0
                    }
                
                return {
                    "total_requests": stats["total_requests"] or 0,
                    "success_count": stats["success_count"] or 0,
                    "failure_count": stats["failure_count"] or 0,
                    "avg_response_time": round(float(stats["avg_response_time"] or 0), 2),
                    "unique_users": stats["unique_users"] or 0,
                    "unique_api_keys": stats["unique_api_keys"] or 0
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching request statistics: {e}")
        raise HTTPException(status_code=500, detail=f"요청 통계 조회 실패: {str(e)}")

@router.get("/admin/request-logs")
def get_request_logs(
    request: Request,
    page: int = Query(1, description="페이지 번호", ge=1),
    limit: int = Query(50, description="페이지당 항목 수", ge=1, le=200),
    user_id: Optional[int] = Query(None, description="사용자 ID 필터"),
    status_code: Optional[int] = Query(None, description="상태 코드 필터"),
    path: Optional[str] = Query(None, description="경로 필터"),
    days: int = Query(7, description="조회할 일수", ge=1, le=90)
):
    """요청 로그 조회"""
    try:
        # 관리자 권한 확인
        current_user = get_current_user_from_request(request)
        if not current_user or not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # WHERE 조건 구성
                where_conditions = [f"request_time >= NOW() - INTERVAL {days} DAY"]
                params = []
                
                if user_id is not None:
                    where_conditions.append("user_id = %s")
                    params.append(user_id)
                
                if status_code is not None:
                    where_conditions.append("status_code = %s")
                    params.append(status_code)
                
                if path:
                    where_conditions.append("path LIKE %s")
                    params.append(f"%{path}%")
                
                where_clause = " AND ".join(where_conditions)
                
                # 전체 개수 조회 - 통합 로그 테이블 사용
                count_query = f"""
                    SELECT COUNT(*) as total FROM (
                        SELECT * FROM request_logs WHERE {where_clause}
                        UNION ALL
                        SELECT * FROM api_request_logs WHERE {where_clause.replace('request_time', 'created_at')}
                    ) as combined_logs
                """
                cursor.execute(count_query, params)
                total_count = cursor.fetchone()["total"]
                
                # 페이지네이션 계산
                offset = (page - 1) * limit
                
                # 로그 데이터 조회
                logs_query = f"""
                    SELECT 
                        combined_logs.id,
                        combined_logs.user_id,
                        combined_logs.api_key,
                        combined_logs.path,
                        combined_logs.method,
                        combined_logs.status_code,
                        combined_logs.response_time,
                        combined_logs.user_agent,
                        combined_logs.request_time,
                        u.email as user_email,
                        u.username as user_username
                    FROM (
                        SELECT id, user_id, api_key, path, method, status_code, response_time, user_agent, request_time FROM request_logs
                        WHERE {where_clause}
                        UNION ALL
                        SELECT id, user_id, api_key, path, method, status_code, response_time, NULL as user_agent, created_at as request_time FROM api_request_logs
                        WHERE {where_clause.replace('request_time', 'created_at')}
                    ) as combined_logs
                    LEFT JOIN users u ON combined_logs.user_id = u.id
                    ORDER BY combined_logs.request_time DESC
                    LIMIT %s OFFSET %s
                """
                
                cursor.execute(logs_query, params + [limit, offset])
                logs = cursor.fetchall()
                
                # 결과 변환
                log_list = []
                for log in logs:
                    log_list.append({
                        "id": log["id"],
                        "user_id": log["user_id"],
                        "api_key": log["api_key"],
                        "path": log["path"],
                        "method": log["method"],
                        "status_code": log["status_code"],
                        "response_time": log["response_time"],
                        "user_agent": log["user_agent"],
                        "request_time": str(log["request_time"]),
                        "user_email": log["user_email"],
                        "user_username": log["user_username"]
                    })
                
                return {
                    "logs": log_list,
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "total": total_count,
                        "pages": (total_count + limit - 1) // limit
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching request logs: {e}")
        raise HTTPException(status_code=500, detail=f"요청 로그 조회 실패: {str(e)}")


@router.get("/admin/dashboard-metrics")
def get_admin_dashboard_metrics(request: Request):
    """관리자 대시보드 메트릭 조회"""
    try:
        # 관리자 권한 확인
        current_user = get_current_user_from_request(request)
        if not current_user or not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. 총 사용자 수
                cursor.execute("SELECT COUNT(*) as total_users FROM users")
                total_users = cursor.fetchone()["total_users"] or 0
                
                # 2. 오늘 신규 사용자
                cursor.execute("""
                    SELECT COUNT(*) as new_users_today 
                    FROM users 
                    WHERE DATE(created_at) = CURDATE()
                """)
                new_users_today = cursor.fetchone()["new_users_today"] or 0
                
                # 3. 현재 활성 사용자 (최근 1시간 내 요청한 사용자)
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as active_users
                    FROM (
                        SELECT user_id FROM request_logs 
                        WHERE request_time >= NOW() - INTERVAL 1 HOUR
                        AND user_id IS NOT NULL
                        UNION ALL
                        SELECT user_id FROM api_request_logs 
                        WHERE created_at >= NOW() - INTERVAL 1 HOUR
                        AND user_id IS NOT NULL
                    ) as combined_logs
                """)
                active_users = cursor.fetchone()["active_users"] or 0
                
                # 4. 총 요청 수 및 성공률 - 통합 로그 테이블 사용
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_requests,
                        COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0) as success_count
                    FROM (
                        SELECT status_code FROM request_logs
                        UNION ALL
                        SELECT status_code FROM api_request_logs
                    ) as combined_logs
                """)
                request_stats = cursor.fetchone()
                total_requests = request_stats["total_requests"] or 0
                success_count = request_stats["success_count"] or 0
                success_rate = (success_count / total_requests * 100) if total_requests > 0 else 0
                
                # 5. 월간 수익 (이번 달 결제 완료 금액)
                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) as revenue
                    FROM payment_logs 
                    WHERE status = 'completed' 
                    AND DATE_FORMAT(created_at, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
                """)
                revenue = cursor.fetchone()["revenue"]
                
                # 6. 플랜별 사용자 분포
                # 먼저 모든 플랜 조회
                cursor.execute("""
                    SELECT id, display_name, name
                    FROM plans
                    ORDER BY id
                """)
                all_plans = cursor.fetchall()
                
                # 각 플랜별 사용자 수 조회
                cursor.execute("""
                    SELECT 
                        p.display_name as plan_name,
                        COUNT(u.id) as user_count
                    FROM users u
                    LEFT JOIN plans p ON u.plan_id = p.id
                    GROUP BY p.id, p.display_name
                """)
                plan_user_counts = {row["plan_name"] or "Free": row["user_count"] for row in cursor.fetchall()}
                
                # 전체 사용자 수 계산
                total_users_for_distribution = sum(plan_user_counts.values())
                
                # 플랜별 색상 매핑
                plan_colors = {
                    "Free": "#8884d8",
                    "Basic": "#82ca9d", 
                    "Pro": "#ffc658",
                    "Enterprise": "#ff7300",
                    "Starter": "#1976d2",
                    "Plus": "#2e7d32"
                }
                
                # 모든 플랜에 대해 분포 계산 (사용자가 없는 플랜도 0%로 표시)
                plan_distribution = []
                for plan in all_plans:
                    plan_name = plan["display_name"] or plan["name"] or "Free"
                    user_count = plan_user_counts.get(plan_name, 0)
                    percentage = (user_count / total_users_for_distribution * 100) if total_users_for_distribution > 0 else 0
                    
                    plan_distribution.append({
                        "name": plan_name,
                        "value": round(percentage, 1),
                        "count": user_count,
                        "color": plan_colors.get(plan_name, "#1976d2")
                    })
                
                # 사용자 수 기준으로 정렬
                plan_distribution.sort(key=lambda x: x["count"], reverse=True)
                
                return {
                    "success": True,
                    "data": {
                        "totalUsers": total_users,
                        "newUsersToday": new_users_today,
                        "activeUsers": active_users,
                        "totalRequests": total_requests,
                        "successRate": round(success_rate, 1),
                        "revenue": revenue,
                        "planDistribution": plan_distribution
                    }
                }
                
    except Exception as e:
        logger.error(f"관리자 대시보드 메트릭 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="메트릭 조회에 실패했습니다")


@router.get("/admin/endpoint-usage")
def get_endpoint_usage(
    request: Request,
    days: int = Query(7, description="조회할 일수", ge=1, le=90)
):
    """엔드포인트별 사용량 조회"""
    try:
        # 관리자 권한 확인
        current_user = get_current_user_from_request(request)
        if not current_user or not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 전체 요청 수 조회 - 통합 로그 테이블 사용
                total_query = f"""
                    SELECT COUNT(*) as total
                    FROM (
                        SELECT * FROM request_logs
                        WHERE request_time >= NOW() - INTERVAL {days} DAY
                        UNION ALL
                        SELECT * FROM api_request_logs
                        WHERE created_at >= NOW() - INTERVAL {days} DAY
                    ) as combined_logs
                """
                cursor.execute(total_query)
                total_requests = cursor.fetchone()["total"]
                
                if total_requests == 0:
                    return {"endpoint_usage": []}
                
                # 엔드포인트별 사용량 조회 - 통합 로그 테이블 사용
                usage_query = f"""
                    SELECT 
                        path as endpoint,
                        COUNT(*) as requests,
                        AVG(response_time) as avg_response_time
                    FROM (
                        SELECT path, response_time FROM request_logs
                        WHERE request_time >= NOW() - INTERVAL {days} DAY
                        UNION ALL
                        SELECT path, response_time FROM api_request_logs
                        WHERE created_at >= NOW() - INTERVAL {days} DAY
                    ) as combined_logs
                    GROUP BY path
                    ORDER BY requests DESC
                    LIMIT 20
                """
                cursor.execute(usage_query)
                endpoints = cursor.fetchall()
                
                endpoint_usage = []
                for endpoint in endpoints:
                    percentage = round((endpoint["requests"] / total_requests) * 100, 2)
                    endpoint_usage.append({
                        "endpoint": endpoint["endpoint"],
                        "requests": endpoint["requests"],
                        "avg_response_time": round(float(endpoint["avg_response_time"] or 0), 2),
                        "percentage": percentage
                    })
                
                return {"endpoint_usage": endpoint_usage}
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching endpoint usage: {e}")
        raise HTTPException(status_code=500, detail=f"엔드포인트 사용량 조회 실패: {str(e)}")


@router.get("/admin/realtime-monitoring")
def get_realtime_monitoring(request: Request):
    """실시간 모니터링 데이터 조회"""
    try:
        current_user = get_current_user_from_request(request)
        if not current_user or not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. API 상태 (각 엔드포인트별 최근 상태) - 두 테이블을 별도로 조회 후 합치기
                # request_logs 테이블 조회
                cursor.execute(get_api_status_query(get_time_filter(1)))
                request_logs_data = cursor.fetchall()
                
                # api_request_logs 테이블 조회
                cursor.execute(get_api_status_query_api_logs(get_time_filter(1)))
                api_request_logs_data = cursor.fetchall()
                
                # 두 결과를 합치기
                combined_data = {}
                
                # request_logs 데이터 추가
                for row in request_logs_data:
                    endpoint = row["endpoint"]
                    combined_data[endpoint] = {
                        "endpoint": endpoint,
                        "total_requests": row["total_requests"],
                        "success_count": row["success_count"],
                        "error_count": row["error_count"],
                        "avg_response_time": row["avg_response_time"],
                        "last_request_time": row["last_request_time"]
                    }
                
                # api_request_logs 데이터 추가/합치기
                for row in api_request_logs_data:
                    endpoint = row["endpoint"]
                    if endpoint in combined_data:
                        # 기존 데이터와 합치기
                        combined_data[endpoint]["total_requests"] += row["total_requests"]
                        combined_data[endpoint]["success_count"] += row["success_count"]
                        combined_data[endpoint]["error_count"] += row["error_count"]
                        # 평균 응답시간은 가중평균으로 계산 (간단히 평균)
                        combined_data[endpoint]["avg_response_time"] = (combined_data[endpoint]["avg_response_time"] + row["avg_response_time"]) / 2
                        # 더 최근 시간으로 업데이트
                        if row["last_request_time"] > combined_data[endpoint]["last_request_time"]:
                            combined_data[endpoint]["last_request_time"] = row["last_request_time"]
                    else:
                        # 새로운 엔드포인트 추가
                        combined_data[endpoint] = {
                            "endpoint": endpoint,
                            "total_requests": row["total_requests"],
                            "success_count": row["success_count"],
                            "error_count": row["error_count"],
                            "avg_response_time": row["avg_response_time"],
                            "last_request_time": row["last_request_time"]
                        }
                
                # 최종 결과 생성
                api_status = []
                for data in combined_data.values():
                    success_rate = (data["success_count"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                    api_status.append({
                        "endpoint": data["endpoint"],
                        "total_requests": data["total_requests"],
                        "success_count": data["success_count"],
                        "error_count": data["error_count"],
                        "success_rate": round(success_rate, 2),
                        "avg_response_time": round(data["avg_response_time"], 2),
                        "last_request_time": data["last_request_time"].isoformat() if data["last_request_time"] else None,
                        "status": "healthy" if success_rate >= 95 else "warning" if success_rate >= 80 else "critical"
                    })
                
                # 요청 수로 정렬
                api_status.sort(key=lambda x: x["total_requests"], reverse=True)
                
                # 2. 응답 시간 분포 (최근 1시간, 5분 단위) - 공통 함수 사용
                cursor.execute(get_response_time_query(get_time_filter(1), "5분", 12))
                response_time_data = []
                for row in cursor.fetchall():
                    response_time_data.append({
                        "time": row["time_bucket"],
                        "avg_response_time": round(row["avg_response_time"], 2),
                        "max_response_time": round(row["max_response_time"], 2),
                        "min_response_time": round(row["min_response_time"], 2),
                        "request_count": row["request_count"]
                    })
                response_time_data.reverse()  # 시간순으로 정렬
                
                # 3. 에러율 (최근 1시간, 5분 단위) - 공통 함수 사용
                cursor.execute(get_error_rate_query(get_time_filter(1), "5분", 12))
                error_rate_data = []
                for row in cursor.fetchall():
                    error_rate = (row["error_count"] / row["total_requests"] * 100) if row["total_requests"] > 0 else 0
                    error_rate_data.append({
                        "time": row["time_bucket"],
                        "total_requests": row["total_requests"],
                        "error_count": row["error_count"],
                        "error_rate": round(error_rate, 2)
                    })
                error_rate_data.reverse()  # 시간순으로 정렬
                
                # 4. TPS (Transactions Per Second) - 최근 1시간, 1분 단위 - 공통 함수 사용
                cursor.execute(get_tps_query(get_time_filter(1), 60))
                tps_data = []
                for row in cursor.fetchall():
                    tps_data.append({
                        "time": row["time_bucket"],
                        "tps": round(row["request_count"] / 60, 2)  # 1분당 요청수를 초당으로 변환
                    })
                tps_data.reverse()  # 시간순으로 정렬
                
                # 5. 전체 시스템 상태 요약 - 공통 함수 사용
                cursor.execute(get_system_summary_query(get_time_filter(1)))
                summary = cursor.fetchone()
                
                system_summary = {
                    "total_requests_1h": summary["total_requests_1h"] or 0,
                    "success_requests_1h": summary["success_requests_1h"] or 0,
                    "error_requests_1h": summary["error_requests_1h"] or 0,
                    "avg_response_time_1h": round(summary["avg_response_time_1h"] or 0, 2),
                    "unique_users_1h": summary["unique_users_1h"] or 0,
                    "success_rate_1h": round((summary["success_requests_1h"] / summary["total_requests_1h"] * 100) if summary["total_requests_1h"] > 0 else 0, 2),
                    "error_rate_1h": round((summary["error_requests_1h"] / summary["total_requests_1h"] * 100) if summary["total_requests_1h"] > 0 else 0, 2)
                }
                
                return {
                    "success": True,
                    "data": {
                        "api_status": api_status,
                        "response_time_data": response_time_data,
                        "error_rate_data": error_rate_data,
                        "tps_data": tps_data,
                        "system_summary": system_summary,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"실시간 모니터링 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="실시간 모니터링 데이터 조회에 실패했습니다")


@router.get("/admin/system-stats")
async def get_system_stats(
    days: int = Query(7, description="조회할 일수 (기본값: 7일)"),
    current_user: dict = Depends(get_current_user_from_request)
):
    """
    시스템 통계 데이터 조회 (일별 요청 수, 성공/실패, 활성 사용자)
    """
    try:
        # 관리자 권한 확인
        if not current_user or not current_user.get('is_admin'):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 일별 시스템 통계 조회 (request_logs만 사용)
                cursor.execute("""
                    SELECT 
                        DATE(request_time) as date,
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) as successful_requests,
                        SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as failed_requests,
                        COUNT(DISTINCT user_id) as active_users
                    FROM request_logs 
                    WHERE request_time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    GROUP BY DATE(request_time)
                    ORDER BY date DESC
                """, (days,))
                
                stats = cursor.fetchall()
                
                # 데이터 포맷팅
                formatted_stats = []
                for stat in stats:
                    formatted_stats.append({
                        "date": stat['date'].strftime('%Y-%m-%d'),
                        "totalRequests": stat['total_requests'],
                        "successfulRequests": stat['successful_requests'],
                        "failedRequests": stat['failed_requests'],
                        "activeUsers": stat['active_users']
                    })
                
                return {
                    "success": True,
                    "data": formatted_stats
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"시스템 통계 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="시스템 통계 데이터를 불러올 수 없습니다.")


@router.get("/admin/user-growth")
async def get_user_growth(
    months: int = Query(6, description="조회할 월수 (기본값: 6개월)"),
    current_user: dict = Depends(get_current_user_from_request)
):
    """
    사용자 증가 데이터 조회 (월별 신규 사용자, 총 사용자)
    """
    try:
        # 관리자 권한 확인
        if not current_user or not current_user.get('is_admin'):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 월별 사용자 증가 데이터 조회
                cursor.execute("""
                    SELECT 
                        DATE_FORMAT(created_at, '%%Y-%%m') as month,
                        COUNT(*) as new_users,
                        SUM(COUNT(*)) OVER (ORDER BY DATE_FORMAT(created_at, '%%Y-%%m')) as total_users
                    FROM users 
                    WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                    GROUP BY DATE_FORMAT(created_at, '%%Y-%%m')
                    ORDER BY month ASC
                """, (months,))
                
                growth_data = cursor.fetchall()
                
                # 데이터 포맷팅
                formatted_data = []
                for data in growth_data:
                    month_name = data['month'].split('-')[1] + '월'
                    formatted_data.append({
                        "month": month_name,
                        "newUsers": data['new_users'],
                        "totalUsers": data['total_users']
                    })
                
                return {
                    "success": True,
                    "data": formatted_data
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 증가 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="사용자 증가 데이터를 불러올 수 없습니다.")


@router.get("/admin/plan-distribution")
async def get_plan_distribution(
    current_user: dict = Depends(get_current_user_from_request)
):
    """
    요금제 분포 데이터 조회 (요금제별 사용자 수, 수익)
    """
    try:
        # 관리자 권한 확인
        if not current_user or not current_user.get('is_admin'):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 요금제별 사용자/매출 분포 조회 (중복 제거, 월간 매출 집계)
                cursor.execute("""
                    SELECT 
                        p.display_name AS name,
                        p.price,
                        COALESCE(u_stats.user_count, 0) AS users,
                        COALESCE(u_inactive_stats.inactive_count, 0) AS inactive_users,
                        COALESCE(r_stats.revenue, 0) AS revenue
                    FROM plans p
                    LEFT JOIN (
                        SELECT plan_id, COUNT(*) AS user_count
                        FROM users
                        GROUP BY plan_id
                    ) u_stats ON u_stats.plan_id = p.id
                    LEFT JOIN (
                        SELECT plan_id, COUNT(*) AS inactive_count
                        FROM users
                        WHERE (is_active = 0 OR is_active = FALSE)
                        GROUP BY plan_id
                    ) u_inactive_stats ON u_inactive_stats.plan_id = p.id
                    LEFT JOIN (
                        SELECT u.plan_id, SUM(pl.amount) AS revenue
                        FROM payment_logs pl
                        JOIN users u ON pl.user_id = u.id
                        WHERE pl.status = 'completed'
                          AND DATE_FORMAT(pl.created_at, '%%Y-%%m') = DATE_FORMAT(NOW(), '%%Y-%%m')
                        GROUP BY u.plan_id
                    ) r_stats ON r_stats.plan_id = p.id
                    ORDER BY users DESC
                """)
                
                plan_data = cursor.fetchall()
                
                # 총 사용자 수 계산
                total_users = sum(plan['users'] for plan in plan_data)
                
                # 데이터 포맷팅
                formatted_data = []
                for plan in plan_data:
                    percentage = (plan['users'] / total_users * 100) if total_users > 0 else 0
                    formatted_data.append({
                        "name": plan['name'],
                        "value": round(percentage, 1),
                        "users": plan['users'],
                        "inactiveUsers": plan.get('inactive_users', 0),
                        "revenue": float(plan['revenue']) if plan['revenue'] else 0
                    })
                
                return {
                    "success": True,
                    "data": formatted_data
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"요금제 분포 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="요금제 분포 데이터를 불러올 수 없습니다.")


@router.get("/admin/error-stats")
async def get_error_stats(
    days: int = Query(7, description="조회할 일수 (기본값: 7일)"),
    current_user: dict = Depends(get_current_user_from_request)
):
    """
    에러 통계 데이터 조회 (에러 타입별 발생 횟수, 비율)
    """
    try:
        # 관리자 권한 확인
        if not current_user or not current_user.get('is_admin'):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 에러 통계 조회 (request_logs만 사용)
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN status_code = 408 THEN '타임아웃'
                            WHEN status_code = 400 THEN '잘못된 입력'
                            WHEN status_code = 500 THEN '서버 오류'
                            WHEN status_code = 503 THEN '서비스 불가'
                            WHEN status_code BETWEEN 400 AND 499 THEN '클라이언트 오류'
                            WHEN status_code BETWEEN 500 AND 599 THEN '서버 오류'
                            ELSE '기타 오류'
                        END as error_type,
                        COUNT(*) as count
                    FROM request_logs 
                    WHERE request_time >= DATE_SUB(CURDATE(), INTERVAL %s DAY) 
                    AND status_code >= 400
                    GROUP BY error_type
                    ORDER BY count DESC
                """, (days,))
                
                error_data = cursor.fetchall()
                
                # 총 에러 수 계산
                total_errors = sum(error['count'] for error in error_data)
                
                # 데이터 포맷팅
                formatted_data = []
                for error in error_data:
                    percentage = (error['count'] / total_errors * 100) if total_errors > 0 else 0
                    formatted_data.append({
                        "type": error['error_type'],
                        "count": error['count'],
                        "percentage": round(percentage, 1)
                    })
                
                return {
                    "success": True,
                    "data": formatted_data
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"에러 통계 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="에러 통계 데이터를 불러올 수 없습니다.")
