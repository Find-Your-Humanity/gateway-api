from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime, date, timedelta
import json
from pydantic import BaseModel
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Pydantic 모델들
class PlanResponse(BaseModel):
    id: int
    name: str
    price: float
    request_limit: int
    description: Optional[str]
    features: dict
    rate_limit_per_minute: int
    is_popular: bool
    sort_order: int

class CurrentPlanResponse(BaseModel):
    plan: PlanResponse
    current_usage: dict
    billing_info: dict
    pending_changes: Optional[dict] = None

class UsageResponse(BaseModel):
    date: str
    tokens_used: int
    api_calls: int
    overage_tokens: int
    overage_cost: float

class PlanChangeRequest(BaseModel):
    plan_id: int

class PaymentRequest(BaseModel):
    plan_id: int
    payment_method: str = "card"  # card, bank_transfer, etc.
    payment_token: Optional[str] = None  # 결제 토큰 (토스페이먼츠, 아임포트 등)

class PaymentResponse(BaseModel):
    success: bool
    payment_id: Optional[str] = None
    message: str
    redirect_url: Optional[str] = None

@router.get("/plans", response_model=List[PlanResponse])
async def get_available_plans():
    """사용 가능한 요금제 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, name, price, request_limit, description, features, 
                   rate_limit_per_minute, is_popular, sort_order
            FROM plans 
            WHERE is_active = TRUE 
            ORDER BY sort_order, price
        """)
        
        plans = []
        for row in cursor.fetchall():
            # features 컬럼은 JSON 또는 빈 문자열/NULL일 수 있으므로 안전하게 파싱
            raw_features = row[5]
            features_dict = {}
            if raw_features is not None:
                try:
                    text_features = raw_features.decode("utf-8") if isinstance(raw_features, (bytes, bytearray, memoryview)) else str(raw_features)
                    text_features = text_features.strip()
                    if text_features:
                        features_dict = json.loads(text_features)
                except Exception:
                    features_dict = {}
            plan = {
                "id": row[0],
                "name": row[1],
                "price": float(row[2]),
                "request_limit": row[3],
                "description": row[4],
                "features": features_dict,
                "rate_limit_per_minute": row[6],
                "is_popular": bool(row[7]),
                "sort_order": row[8]
            }
            plans.append(plan)
        
        return plans
    finally:
        cursor.close()
        conn.close()

@router.get("/current-plan", response_model=CurrentPlanResponse)
async def get_current_plan(user=Depends(get_current_user_from_request)):
    """현재 사용자의 요금제 정보 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 현재 사용자의 플랜 정보 조회 (users.plan_id 우선)
        cursor.execute("""
            SELECT p.id, p.name, p.price, p.request_limit, p.description, p.features,
                   p.rate_limit_per_minute, p.is_popular, p.sort_order
            FROM users u
            JOIN plans p ON u.plan_id = p.id
            WHERE u.id = %s
        """, (user["id"],))
        
        user_plan = cursor.fetchone()
        
        if not user_plan:
            # 플랜이 없으면 Demo 플랜으로 처리
            cursor.execute("""
                SELECT id, name, price, request_limit, description, features,
                       rate_limit_per_minute, is_popular, sort_order
                FROM plans WHERE name = 'Demo'
            """)
            user_plan = cursor.fetchone()
            
            # Demo 플랜도 없으면 기본값 생성
            if not user_plan:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="기본 요금제를 찾을 수 없습니다."
                )
        
        # features 컬럼 안전 파싱
        raw_features = user_plan[5]
        features_dict = {}
        if raw_features is not None:
            try:
                text_features = raw_features.decode("utf-8") if isinstance(raw_features, (bytes, bytearray, memoryview)) else str(raw_features)
                text_features = text_features.strip()
                if text_features:
                    features_dict = json.loads(text_features)
            except Exception:
                features_dict = {}

        plan = {
            "id": user_plan[0],
            "name": user_plan[1],
            "price": float(user_plan[2]),
            "request_limit": user_plan[3],
            "description": user_plan[4],
            "features": features_dict,
            "rate_limit_per_minute": user_plan[6],
            "is_popular": bool(user_plan[7]),
            "sort_order": user_plan[8]
        }
        
        # 활성 구독 정보 조회 (시작일, 종료일)
        cursor.execute("""
            SELECT start_date, end_date
            FROM user_subscriptions
            WHERE user_id = %s AND start_date <= CURDATE()
            ORDER BY start_date DESC
            LIMIT 1
        """, (user["id"],))
        
        subscription = cursor.fetchone()
        start_date = subscription[0] if subscription else None
        end_date = subscription[1] if subscription else None
        
        # 이번 달 사용량 조회 (request_logs 테이블 사용)
        current_month = date.today().replace(day=1)
        cursor.execute("""
            SELECT COUNT(*) as total_calls,
                   COUNT(CASE WHEN status_code = 200 THEN 1 END) as success_calls,
                   COUNT(CASE WHEN status_code != 200 THEN 1 END) as failed_calls
            FROM request_logs
            WHERE user_id = %s AND request_time >= %s
        """, (user["id"], current_month))
        
        usage_data = cursor.fetchone()
        total_calls = usage_data[0] if usage_data else 0
        success_calls = usage_data[1] if usage_data else 0
        failed_calls = usage_data[2] if usage_data else 0
        
        current_usage = {
            "tokens_used": total_calls,  # 요청 수를 토큰 사용량으로 간주
            "api_calls": total_calls,
            "overage_tokens": max(0, total_calls - plan["request_limit"]),
            "overage_cost": 0,  # 초기에는 과금 없음
            "tokens_limit": plan["request_limit"],
            "average_tokens_per_call": 1,  # 요청당 1토큰으로 간주
            "success_rate": (success_calls / total_calls * 100) if total_calls > 0 else 0
        }
        
        # 청구 정보
        billing_info = {
            "base_fee": plan["price"],
            "overage_fee": current_usage["overage_cost"],
            "total_amount": plan["price"] + current_usage["overage_cost"],
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None
        }
        
        # 예정된 변경사항 확인
        cursor.execute("""
            SELECT us.plan_id, p.name, us.start_date
            FROM user_subscriptions us
            JOIN plans p ON us.plan_id = p.id
            WHERE us.user_id = %s AND us.start_date > CURDATE()
            ORDER BY us.start_date ASC
            LIMIT 1
        """, (user["id"],))
        
        pending_change = cursor.fetchone()
        pending_changes = None
        if pending_change:
            pending_changes = {
                "plan_id": pending_change[0],
                "plan_name": pending_change[1],
                "effective_date": pending_change[2].isoformat()
            }
        
        return {
            "plan": plan,
            "current_usage": current_usage,
            "billing_info": billing_info,
            "pending_changes": pending_changes
        }
    finally:
        cursor.close()
        conn.close()

@router.get("/usage", response_model=List[UsageResponse])
async def get_usage_history(
    user=Depends(get_current_user_from_request),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """사용량 히스토리 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT DATE(request_time) as date, 
                   COUNT(*) as api_calls,
                   COUNT(CASE WHEN status_code = 200 THEN 1 END) as success_calls
            FROM request_logs
            WHERE user_id = %s
        """
        params = [user["id"]]
        
        if start_date:
            query += " AND DATE(request_time) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(request_time) <= %s"
            params.append(end_date)
        
        query += " GROUP BY DATE(request_time) ORDER BY date DESC LIMIT 30"
        
        cursor.execute(query, params)
        
        usage_history = []
        for row in cursor.fetchall():
            usage_history.append({
                "date": row[0].isoformat(),
                "tokens_used": row[1],  # api_calls를 tokens_used로 사용
                "api_calls": row[1],
                "overage_tokens": 0,  # 초기에는 과금 없음
                "overage_cost": 0.0
            })
        
        return usage_history
    finally:
        cursor.close()
        conn.close()

@router.post("/change-plan")
async def change_plan(
    request: PlanChangeRequest,
    user=Depends(get_current_user_from_request)
):
    """요금제 변경 (다음 청구 주기부터 적용)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 플랜 존재 확인
        cursor.execute("SELECT id, name FROM plans WHERE id = %s AND is_active = TRUE", (request.plan_id,))
        plan = cursor.fetchone()
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="요금제를 찾을 수 없습니다."
            )
        
        # 다음 달 1일 계산
        today = date.today()
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        
        # 기존 활성 구독이 있으면 다음 달부터 종료
        cursor.execute("""
            SELECT id FROM user_subscriptions 
            WHERE user_id = %s AND end_date IS NULL
        """, (user["id"],))
        
        existing_subscription = cursor.fetchone()
        if existing_subscription:
            cursor.execute("""
                UPDATE user_subscriptions 
                SET end_date = %s
                WHERE id = %s
            """, (next_month - timedelta(days=1), existing_subscription[0]))
        
        # 새 구독 생성 (다음 달 1일부터 시작)
        cursor.execute("""
            INSERT INTO user_subscriptions (user_id, plan_id, start_date)
            VALUES (%s, %s, %s)
        """, (user["id"], request.plan_id, next_month))
        
        # users 테이블의 plan_id도 업데이트 (즉시 반영)
        cursor.execute("""
            UPDATE users SET plan_id = %s WHERE id = %s
        """, (request.plan_id, user["id"]))
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"{plan[1]} 요금제로 변경되었습니다. {next_month.strftime('%Y년 %m월 1일')}부터 적용됩니다.",
            "plan_id": request.plan_id,
            "effective_date": next_month.isoformat()
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="요금제 변경 중 오류가 발생했습니다."
        )
    finally:
        cursor.close()
        conn.close()

@router.post("/purchase-plan", response_model=PaymentResponse)
async def purchase_plan(
    request: PaymentRequest,
    user=Depends(get_current_user_from_request)
):
    """요금제 구매 (결제 API 연동)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 플랜 존재 확인
        cursor.execute("SELECT id, name, price FROM plans WHERE id = %s AND is_active = TRUE", (request.plan_id,))
        plan = cursor.fetchone()
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="요금제를 찾을 수 없습니다."
            )
        
        # TODO: 실제 결제 API 연동
        # 1. 결제 토큰 검증
        # 2. 결제 처리
        # 3. 결제 성공 시 플랜 변경
        
        # 임시로 결제 성공으로 처리
        payment_id = f"PAY_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user['id']}"
        
        # 결제 로그 기록
        cursor.execute("""
            INSERT INTO payment_logs (user_id, plan_id, amount, paid_at)
            VALUES (%s, %s, %s, NOW())
        """, (user["id"], request.plan_id, plan[2]))
        
        # 플랜 즉시 변경 (결제 완료 시)
        cursor.execute("""
            UPDATE users SET plan_id = %s WHERE id = %s
        """, (request.plan_id, user["id"]))
        
        # 활성 구독 생성
        cursor.execute("""
            INSERT INTO user_subscriptions (user_id, plan_id, start_date)
            VALUES (%s, %s, CURDATE())
        """, (user["id"], request.plan_id))
        
        conn.commit()
        
        return {
            "success": True,
            "payment_id": payment_id,
            "message": f"{plan[1]} 요금제 구매가 완료되었습니다.",
            "redirect_url": None
        }
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="결제 처리 중 오류가 발생했습니다."
        )
    finally:
        cursor.close()
        conn.close()

@router.get("/usage-stats")
async def get_usage_stats(user=Depends(get_current_user_from_request)):
    """사용량 통계 조회 (실시간 + 지난달)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 이번 달 사용량
        current_month = date.today().replace(day=1)
        cursor.execute("""
            SELECT COUNT(*) as total_calls,
                   COUNT(CASE WHEN status_code = 200 THEN 1 END) as success_calls
            FROM request_logs
            WHERE user_id = %s AND request_time >= %s
        """, (user["id"], current_month))
        
        current_usage = cursor.fetchone()
        
        # 지난달 사용량
        if current_month.month == 1:
            last_month = date(current_month.year - 1, 12, 1)
        else:
            last_month = date(current_month.year, current_month.month - 1, 1)
        
        cursor.execute("""
            SELECT COUNT(*) as total_calls,
                   COUNT(CASE WHEN status_code = 200 THEN 1 END) as success_calls
            FROM request_logs
            WHERE user_id = %s AND request_time >= %s AND request_time < %s
        """, (user["id"], last_month, current_month))
        
        last_month_usage = cursor.fetchone()
        
        return {
            "current_month": {
                "tokens_used": current_usage[0] if current_usage else 0,
                "api_calls": current_usage[0] if current_usage else 0,
                "overage_cost": 0.0
            },
            "last_month": {
                "tokens_used": last_month_usage[0] if last_month_usage else 0,
                "api_calls": last_month_usage[0] if last_month_usage else 0,
                "overage_cost": 0.0
            }
        }
    finally:
        cursor.close()
        conn.close()
