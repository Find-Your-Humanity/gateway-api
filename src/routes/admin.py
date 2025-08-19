"""
관리자 전용 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from src.config.database import get_db_connection
from src.utils.auth import get_password_hash
from src.routes.auth import get_current_user_from_request
from fastapi import Request

router = APIRouter()

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

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    name: Optional[str] = None
    contact: Optional[str] = None
    is_admin: bool = False

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
    price: float
    request_limit: int
    description: Optional[str] = None

class PlanCreate(BaseModel):
    name: str
    price: float
    request_limit: int
    description: Optional[str] = None

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    request_limit: Optional[int] = None
    description: Optional[str] = None

# 관리자 권한 확인 의존성
def require_admin(request: Request):
    """관리자 권한이 필요한 엔드포인트용 의존성"""
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    
    if not (user.get('is_admin') == 1 or user.get('is_admin') == True):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    return user

# ==================== 사용자 관리 API ====================

@router.get("/admin/users", response_model=List[UserResponse])
def get_users(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    admin_user = Depends(require_admin)
):
    """사용자 목록 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 검색 조건 구성
                where_clause = "WHERE 1=1"
                params = []
                
                if search:
                    where_clause += " AND (email LIKE %s OR username LIKE %s OR name LIKE %s)"
                    search_param = f"%{search}%"
                    params.extend([search_param, search_param, search_param])
                
                # 총 개수 조회
                cursor.execute(f"SELECT COUNT(*) FROM users {where_clause}", params)
                total = cursor.fetchone()[0]
                
                # 페이지네이션된 데이터 조회
                offset = (page - 1) * limit
                query = f"""
                    SELECT id, email, username, name, contact, is_active, is_admin, created_at 
                    FROM users {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, offset])
                cursor.execute(query, params)
                users = cursor.fetchall()
                
                return {
                    "success": True,
                    "data": users,
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "total": total,
                        "pages": (total + limit - 1) // limit
                    }
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 목록 조회 실패: {e}")

@router.post("/admin/users", response_model=UserResponse)
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
                    INSERT INTO users (email, username, password_hash, name, contact, is_admin, is_verified)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE)
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

@router.get("/admin/plans", response_model=List[PlanResponse])
def get_plans(
    request: Request,
    admin_user = Depends(require_admin)
):
    """요금제 목록 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, name, price, request_limit, description FROM plans ORDER BY price")
                plans = cursor.fetchall()
                return {"success": True, "data": plans}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 목록 조회 실패: {e}")

@router.post("/admin/plans", response_model=PlanResponse)
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
                    SELECT us.id, us.start_date, us.end_date, p.id as plan_id, p.name as plan_name, 
                           p.price, p.request_limit, p.description
                    FROM user_subscriptions us
                    JOIN plans p ON us.plan_id = p.id
                    WHERE us.user_id = %s AND (us.end_date IS NULL OR us.end_date >= CURDATE())
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
    plan_id: int,
    request: Request,
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
                
                cursor.execute("SELECT id FROM plans WHERE id = %s", (plan_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다.")
                
                # 기존 활성 구독 종료
                cursor.execute("""
                    UPDATE user_subscriptions 
                    SET end_date = CURDATE() 
                    WHERE user_id = %s AND (end_date IS NULL OR end_date >= CURDATE())
                """, (user_id,))
                
                # 새 구독 생성
                cursor.execute("""
                    INSERT INTO user_subscriptions (user_id, plan_id, start_date)
                    VALUES (%s, %s, CURDATE())
                """, (user_id, plan_id))
                
                conn.commit()
                
                return {"success": True, "message": "요금제가 할당되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요금제 할당 실패: {e}")
