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

@router.get("/test-db")
async def test_database_connection():
    """데이터베이스 연결 테스트"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                # 1. 기본 연결 테스트
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                print(f"✅ 기본 연결 테스트: {result}")
                
                # 2. plans 테이블 존재 확인
                cursor.execute("SHOW TABLES LIKE 'plans'")
                plans_table = cursor.fetchone()
                print(f"✅ plans 테이블 존재: {plans_table is not None}")
                
                # 3. plans 테이블 구조 확인
                if plans_table:
                    cursor.execute("DESCRIBE plans")
                    columns = cursor.fetchall()
                    print(f"✅ plans 테이블 컬럼: {len(columns)}개")
                    for col in columns:
                        print(f"  - {col['Field']}: {col['Type']}")
                
                # 4. plans 테이블 데이터 확인
                cursor.execute("SELECT COUNT(*) as count FROM plans")
                count_result = cursor.fetchone()
                print(f"✅ plans 테이블 데이터: {count_result['count']}개")
                
                # 5. plans 테이블 상세 데이터 확인
                cursor.execute("SELECT id, name, is_active FROM plans")
                plans_data = cursor.fetchall()
                print(f"✅ plans 테이블 상세:")
                for plan in plans_data:
                    print(f"  - ID: {plan['id']}, Name: {plan['name']}, Active: {plan['is_active']}")
                
                return {
                    "success": True,
                    "message": "데이터베이스 연결 성공",
                    "plans_count": count_result['count'] if count_result else 0,
                    "plans_data": plans_data
                }
        
    except Exception as e:
        print(f"❌ 데이터베이스 테스트 오류: {e}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "message": "데이터베이스 연결 실패"
        }

@router.get("/test-sql")
async def test_sql_query():
    """SQL 쿼리 테스트"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                # 1. 모든 plans 데이터 조회
                cursor.execute("SELECT * FROM plans")
                all_plans = cursor.fetchall()
                print(f"✅ 모든 plans: {len(all_plans)}개")
                
                # 2. is_active = 1 조건으로 조회
                cursor.execute("SELECT * FROM plans WHERE is_active = 1")
                active_plans = cursor.fetchall()
                print(f"✅ is_active = 1: {len(active_plans)}개")
                
                # 3. is_active = TRUE 조건으로 조회
                cursor.execute("SELECT * FROM plans WHERE is_active = TRUE")
                true_plans = cursor.fetchall()
                print(f"✅ is_active = TRUE: {len(true_plans)}개")
                
                # 4. is_active = FALSE 조건으로 조회
                cursor.execute("SELECT * FROM plans WHERE is_active = FALSE")
                false_plans = cursor.fetchall()
                print(f"✅ is_active = FALSE: {len(false_plans)}개")
                
                # 5. is_active = 0 조건으로 조회
                cursor.execute("SELECT * FROM plans WHERE is_active = 0")
                zero_plans = cursor.fetchall()
                print(f"✅ is_active = 0: {len(zero_plans)}개")
                
                return {
                    "success": True,
                    "all_plans_count": len(all_plans),
                    "active_plans_count": len(active_plans),
                    "true_plans_count": len(true_plans),
                    "false_plans_count": len(false_plans),
                    "zero_plans_count": len(zero_plans),
                    "active_plans": active_plans
                }
        
    except Exception as e:
        print(f"❌ SQL 테스트 오류: {e}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "message": "SQL 테스트 실패"
        }

@router.get("/plans", response_model=List[PlanResponse])
async def get_available_plans():
    """사용 가능한 요금제 목록 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                print(f"🔍 plans 테이블 조회 시작...")
                
                cursor.execute("""
                    SELECT id, name, price, monthly_request_limit, description, features, 
                           rate_limit_per_minute, is_popular, sort_order
                    FROM plans 
                    WHERE is_active = 1 
                    ORDER BY sort_order, price
                """)
                
                print(f"✅ SQL 쿼리 실행 완료")
                
                plans = []
                rows = cursor.fetchall()
                print(f"📊 조회된 행 수: {len(rows)}")
                
                for row in rows:
                    try:
                        print(f"🔍 행 처리 중: {row}")
                        # features 컬럼은 JSON 또는 빈 문자열/NULL일 수 있으므로 안전하게 파싱
                        raw_features = row['features']
                        features_dict = {}
                        if raw_features is not None:
                            try:
                                text_features = raw_features.decode("utf-8") if isinstance(raw_features, (bytes, bytearray, memoryview)) else str(raw_features)
                                text_features = text_features.strip()
                                if text_features:
                                    features_dict = json.loads(text_features)
                                    print(f"✅ features 파싱 성공: {features_dict}")
                            except Exception as e:
                                print(f"⚠️ features 파싱 오류 (row {row['id']}): {e}")
                                features_dict = {}
                        
                        plan = {
                            "id": row['id'],
                            "name": row['name'],
                            "price": float(row['price']),
                            "request_limit": row['monthly_request_limit'] or 0,  # monthly_request_limit을 request_limit로 매핑
                            "description": row['description'],
                            "features": features_dict,
                            "rate_limit_per_minute": row['rate_limit_per_minute'],
                            "is_popular": bool(row['is_popular']),
                            "sort_order": row['sort_order']
                        }
                        print(f"✅ 플랜 생성 완료: {plan['name']}")
                        plans.append(plan)
                    except Exception as e:
                        print(f"❌ 행 처리 오류 (row {row}): {e}")
                        continue
                
                print(f"✅ 요금제 목록 반환: {len(plans)}개")
                return plans
                
    except Exception as e:
        print(f"❌ get_available_plans 오류: {e}")
        print(f"❌ 오류 타입: {type(e)}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"요금제 목록 조회 중 오류가 발생했습니다: {str(e)}"
        )

@router.get("/current-plan", response_model=CurrentPlanResponse)
async def get_current_plan(user=Depends(get_current_user_from_request)):
    """현재 사용자의 요금제 정보 조회"""
    try:
        print(f"🔍 get_current_plan 호출됨 - 사용자 ID: {user.get('id') if user else 'None'}")
        
        if not user:
            print("❌ 사용자 정보가 없습니다.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증이 필요합니다."
            )
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                print(f"✅ 데이터베이스 연결 성공")
                
                # 현재 사용자의 플랜 정보 조회 (users.plan_id 우선)
                cursor.execute("""
                    SELECT p.id, p.name, p.price, p.monthly_request_limit, p.description, p.features,
                           p.rate_limit_per_minute, p.is_popular, p.sort_order
                    FROM users u
                    JOIN plans p ON u.plan_id = p.id
                    WHERE u.id = %s
                """, (user["id"],))
                
                user_plan = cursor.fetchone()
                print(f"✅ 사용자 플랜 조회: {user_plan}")
                
                if not user_plan:
                    # 플랜이 없으면 기본 플랜으로 처리
                    cursor.execute("""
                        SELECT id, name, price, monthly_request_limit, description, features,
                               rate_limit_per_minute, is_popular, sort_order
                        FROM plans WHERE name = 'free'
                    """)
                    user_plan = cursor.fetchone()
                    print(f"✅ 기본 플랜 조회: {user_plan}")
                    
                    # 기본 플랜도 없으면 첫 번째 플랜 사용
                    if not user_plan:
                        cursor.execute("""
                            SELECT id, name, price, monthly_request_limit, description, features,
                                   rate_limit_per_minute, is_popular, sort_order
                            FROM plans WHERE is_active = 1 ORDER BY sort_order LIMIT 1
                        """)
                        user_plan = cursor.fetchone()
                        print(f"✅ 첫 번째 플랜 조회: {user_plan}")
                        
                        if not user_plan:
                            print("❌ 기본 요금제를 찾을 수 없습니다.")
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="기본 요금제를 찾을 수 없습니다."
                            )
                
                # features 컬럼 안전 파싱
                raw_features = user_plan['features']
                features_dict = {}
                if raw_features is not None:
                    try:
                        text_features = raw_features.decode("utf-8") if isinstance(raw_features, (bytes, bytearray, memoryview)) else str(raw_features)
                        text_features = text_features.strip()
                        if text_features:
                            features_dict = json.loads(text_features)
                    except Exception as e:
                        print(f"⚠️ features 파싱 오류: {e}")
                        features_dict = {}

                plan = {
                    "id": user_plan['id'],
                    "name": user_plan['name'],
                    "price": float(user_plan['price']),
                    "request_limit": user_plan['monthly_request_limit'] or 0,  # monthly_request_limit을 request_limit로 매핑
                    "description": user_plan['description'],
                    "features": features_dict,
                    "rate_limit_per_minute": user_plan['rate_limit_per_minute'],
                    "is_popular": bool(user_plan['is_popular']),
                    "sort_order": user_plan['sort_order']
                }
                
                print(f"✅ 플랜 정보 파싱 완료: {plan['name']}")
                
                # 활성 구독 정보 조회 (시작일, 종료일) - user_subscriptions 테이블이 없을 수 있으므로 안전하게 처리
                start_date = None
                end_date = None
                try:
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
                    print(f"✅ 구독 정보: {start_date} ~ {end_date}")
                except Exception as e:
                    print(f"⚠️ user_subscriptions 테이블 조회 실패 (무시): {e}")
                    # 테이블이 없어도 계속 진행
                
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
                total_calls = usage_data['total_calls'] if usage_data else 0
                success_calls = usage_data['success_calls'] if usage_data else 0
                failed_calls = usage_data['failed_calls'] if usage_data else 0
                print(f"✅ 사용량 정보: 총 {total_calls}회, 성공 {success_calls}회, 실패 {failed_calls}회")
                
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
                
                # 예정된 변경사항 확인 - user_subscriptions 테이블이 없을 수 있으므로 안전하게 처리
                pending_changes = None
                try:
                    cursor.execute("""
                        SELECT us.plan_id, p.name, us.start_date
                        FROM user_subscriptions us
                        JOIN plans p ON us.plan_id = p.id
                        WHERE us.user_id = %s AND us.start_date > CURDATE()
                        ORDER BY us.start_date ASC
                        LIMIT 1
                    """, (user["id"],))
                    
                    pending_change = cursor.fetchone()
                    if pending_change:
                        pending_changes = {
                            "plan_id": pending_change[0],
                            "plan_name": pending_change[1],
                            "effective_date": pending_change[2].isoformat()
                        }
                except Exception as e:
                    print(f"⚠️ 예정된 변경사항 조회 실패 (무시): {e}")
                    # 테이블이 없어도 계속 진행
                
                result = {
                    "plan": plan,
                    "current_usage": current_usage,
                    "billing_info": billing_info,
                    "pending_changes": pending_changes
                }
                
                print(f"✅ get_current_plan 완료: {plan['name']} 플랜")
                return result
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ get_current_plan 오류: {e}")
        print(f"❌ 오류 타입: {type(e)}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"현재 요금제 조회 중 오류가 발생했습니다: {str(e)}"
        )

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
    """요금제 변경 (즉시 적용)"""
    try:
        print(f"🔍 change_plan 호출됨 - 사용자 ID: {user.get('id')}, 플랜 ID: {request.plan_id}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                # 플랜 존재 확인
                cursor.execute("SELECT id, name FROM plans WHERE id = %s AND is_active = 1", (request.plan_id,))
                plan = cursor.fetchone()
                
                if not plan:
                    print(f"❌ 플랜을 찾을 수 없음: {request.plan_id}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="요금제를 찾을 수 없습니다."
                    )
                
                print(f"✅ 플랜 확인: {plan['name']}")
                
                # user_subscriptions 테이블이 없을 수 있으므로 안전하게 처리
                try:
                    # 기존 활성 구독이 있으면 즉시 종료
                    cursor.execute("""
                        UPDATE user_subscriptions 
                        SET end_date = CURDATE(), status = 'cancelled'
                        WHERE user_id = %s AND (end_date IS NULL OR end_date > CURDATE())
                    """, (user["id"],))
                    print(f"✅ 기존 구독 종료 완료")
                    
                    # 새 구독 생성 (즉시 시작)
                    cursor.execute("""
                        INSERT INTO user_subscriptions (user_id, plan_id, start_date, status)
                        VALUES (%s, %s, CURDATE(), 'active')
                    """, (user["id"], request.plan_id))
                    print(f"✅ 새 구독 생성 완료 (즉시 시작)")
                    
                except Exception as e:
                    print(f"⚠️ user_subscriptions 테이블 처리 실패 (무시): {e}")
                    # 테이블이 없어도 계속 진행
                
                # users 테이블의 plan_id 업데이트 (즉시 반영)
                cursor.execute("""
                    UPDATE users SET plan_id = %s WHERE id = %s
                """, (request.plan_id, user["id"]))
                print(f"✅ 사용자 플랜 업데이트 완료")
                
                # 트랜잭션 커밋
                conn.commit()
                
                result = {
                    "success": True,
                    "message": f"{plan['name']} 요금제로 즉시 변경되었습니다.",
                    "plan_id": request.plan_id,
                    "effective_date": "immediate"
                }
                
                print(f"✅ change_plan 완료: {plan['name']} (즉시 적용)")
                return result
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ change_plan 오류: {e}")
        print(f"❌ 오류 타입: {type(e)}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"요금제 변경 중 오류가 발생했습니다: {str(e)}"
        )

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
        cursor.execute("SELECT id, name, price FROM plans WHERE id = %s AND is_active = 1", (request.plan_id,))
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
        cursor.execute("SELECT id, name, price FROM plans WHERE id = %s AND is_active = 1", (request.plan_id,))
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
