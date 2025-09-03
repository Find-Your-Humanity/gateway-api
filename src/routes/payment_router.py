from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from pydantic import BaseModel
import httpx
import base64
import os
import uuid
from datetime import datetime
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

def generate_unique_payment_id() -> str:
    """고유한 결제 ID 생성"""
    return f"PAY_{uuid.uuid4().hex[:16].upper()}"

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Toss Payments 설정
TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "test_gsk_docs_OaPz8L5KdmQXkzRz3y47BMw6")
TOSS_API_URL = "https://api.tosspayments.com/v1/payments/confirm"

# Pydantic 모델들
class PaymentConfirmRequest(BaseModel):
    paymentKey: str
    orderId: str
    amount: int
    plan_id: int

class PaymentCompleteRequest(BaseModel):
    paymentKey: str
    orderId: str
    amount: int
    plan_id: int

class PaymentConfirmResponse(BaseModel):
    success: bool
    message: str
    payment_id: Optional[str] = None
    plan_id: Optional[int] = None

class PaymentCompleteResponse(BaseModel):
    success: bool
    message: str
    payment_id: Optional[str] = None
    plan_id: Optional[int] = None

@router.post("/confirm", response_model=PaymentConfirmResponse)
async def confirm_payment(
    request: PaymentConfirmRequest,
    user=Depends(get_current_user_from_request)
):
    """Toss Payments 결제 승인 처리"""
    try:
        print(f"🔍 결제 승인 요청 - 사용자 ID: {user['id']}, 플랜 ID: {request.plan_id}")
        
        # 1. 결제 승인 (DASHBOARD_DIRECT는 내장 승인 경로)
        payment_data = None
        if request.paymentKey == 'DASHBOARD_DIRECT':
            print("🟦 대시보드 직접 결제 승인(DASHBOARD_DIRECT) 경로")
            payment_data = {
                "paymentKey": request.paymentKey,
                "orderId": request.orderId,
                "approvedAt": datetime.utcnow().isoformat() + 'Z',
                "amount": request.amount,
                "status": "DONE",
                "method": "card",
                "provider": "internal"
            }
        else:
            headers = {
                "Authorization": f"Basic {base64.b64encode(f'{TOSS_SECRET_KEY}:'.encode()).decode()}",
                "Content-Type": "application/json"
            }
            payload = {
                "paymentKey": request.paymentKey,
                "orderId": request.orderId,
                "amount": request.amount
            }
            print(f"📤 Toss Payments API 호출: {payload}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    TOSS_API_URL,
                    headers=headers,
                    json=payload
                )
            print(f"📥 Toss Payments 응답: {response.status_code}")
            if response.status_code != 200:
                print(f"❌ Toss Payments API 오류: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"결제 승인 실패: {response.text}"
                )
            payment_data = response.json()
            print(f"✅ Toss Payments 결제 승인 성공: {payment_data}")
        
        # 2. 결제 성공 시 DB에 구독 정보 저장
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    # 플랜 정보 조회
                    cursor.execute("SELECT id, name, price FROM plans WHERE id = %s AND is_active = 1", (request.plan_id,))
                    plan = cursor.fetchone()
                    
                    if not plan:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="요금제를 찾을 수 없습니다."
                        )
                    
                    # users.plan_id 업데이트
                    cursor.execute("""
                        UPDATE users SET plan_id = %s WHERE id = %s
                    """, (request.plan_id, user["id"]))

                    # 기존 활성 구독 비활성화
                    cursor.execute("""
                        UPDATE user_subscriptions
                        SET status = 'cancelled', end_date = CURDATE()
                        WHERE user_id = %s AND status = 'active'
                    """, (user["id"],))

                    # user_subscriptions에 신규 구독 저장 (upsert 성격)
                    cursor.execute("""
                        INSERT INTO user_subscriptions
                        (user_id, plan_id, start_date, end_date, status, amount, currency, payment_method, current_usage, last_reset_at)
                        VALUES (%s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 1 MONTH), 'active', %s, 'KRW', 'card', 0, NOW())
                    """, (user["id"], request.plan_id, request.amount))

                    subscription_id = cursor.lastrowid

                    # payment_logs에 결제 기록 저장
                    cursor.execute("""
                        INSERT INTO payment_logs (user_id, plan_id, paid_at, amount, payment_method, payment_id, status)
                        VALUES (%s, %s, NOW(), %s, 'card', %s, 'completed')
                    """, (user["id"], request.plan_id, request.amount, request.orderId or request.paymentKey))
                    
                    conn.commit()
                    
                    print(f"✅ DB 저장 완료 - 구독 ID: {subscription_id}")
                    
                    # plan 데이터에서 요금제 이름 추출 (dict 또는 tuple 모두 지원)
                    if isinstance(plan, dict):
                        plan_name = plan.get('name', '요금제')
                    elif plan and len(plan) > 1:
                        plan_name = str(plan[1]) if plan[1] else '요금제'
                    else:
                        plan_name = '요금제'
                    
                    return {
                        "success": True,
                        "message": f"{plan_name} 요금제 구독이 완료되었습니다.",
                        "payment_id": request.paymentKey,
                        "plan_id": request.plan_id
                    }
                    
                except Exception as e:
                    conn.rollback()
                    print(f"❌ DB 저장 오류: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"구독 정보 저장 중 오류가 발생했습니다: {str(e)}"
                    )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 결제 승인 처리 오류: {e}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"결제 승인 처리 중 오류가 발생했습니다: {str(e)}"
        )

@router.post("/complete", response_model=PaymentCompleteResponse)
async def complete_payment(
    request: PaymentCompleteRequest,
    user=Depends(get_current_user_from_request)
):
    """Toss Payments 승인 완료 후 구독 정보 저장"""
    if not user:
        print("❌ 결제 완료 요청: 사용자 인증 실패")
        raise HTTPException(status_code=401, detail="사용자 인증이 필요합니다.")
    
    try:
        print(f"🔍 결제 완료 처리 - 사용자 ID: {user['id']}, 플랜 ID: {request.plan_id}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    # 플랜 정보 조회
                    cursor.execute("SELECT id, name, price FROM plans WHERE id = %s AND is_active = 1", (request.plan_id,))
                    plan = cursor.fetchone()
                    
                    if not plan:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="요금제를 찾을 수 없습니다."
                        )
                    
                    # 중복 결제 처리 방지 (orderId 기준)
                    cursor.execute("""
                        SELECT id FROM payment_logs WHERE payment_id = %s AND user_id = %s
                    """, (request.orderId, user["id"]))
                    
                    existing_payment = cursor.fetchone()
                    if existing_payment:
                        plan_name = plan.get('name', '요금제') if isinstance(plan, dict) else (plan[1] if plan and len(plan) > 1 else '요금제')
                        return {
                            "success": True,
                            "message": f"{plan_name} 요금제 구독이 이미 완료되었습니다.",
                            "payment_id": request.orderId,
                            "plan_id": request.plan_id
                        }
                    
                    # users.plan_id 업데이트
                    cursor.execute("""
                        UPDATE users SET plan_id = %s WHERE id = %s
                    """, (request.plan_id, user["id"]))
                    
                    # user_subscriptions 테이블에 구독 정보 저장
                    cursor.execute("""
                        INSERT INTO user_subscriptions (user_id, plan_id, start_date, end_date, status, amount, currency, payment_method, current_usage, last_reset_at)
                        VALUES (%s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 1 MONTH), 'active', %s, 'KRW', 'card', 0, NOW())
                    """, (user["id"], request.plan_id, request.amount))
                    
                    subscription_id = cursor.lastrowid
                    
                    # 고유한 payment_id 생성
                    unique_payment_id = generate_unique_payment_id()
                    print(f"🔑 생성된 payment_id: {unique_payment_id}")
                    
                    # payment_logs 테이블에 결제 기록 저장
                    try:
                        cursor.execute("""
                            INSERT INTO payment_logs (user_id, plan_id, paid_at, amount, payment_method, payment_id, status)
                            VALUES (%s, %s, NOW(), %s, 'card', %s, 'completed')
                        """, (user["id"], request.plan_id, request.amount, unique_payment_id))
                        print(f"✅ payment_logs 저장 성공: {unique_payment_id}")
                    except Exception as payment_log_error:
                        print(f"❌ payment_logs 저장 실패: {payment_log_error}")
                        print(f"❌ Error type: {type(payment_log_error).__name__}")
                        if hasattr(payment_log_error, 'args'):
                            print(f"❌ Error args: {payment_log_error.args}")
                        if hasattr(payment_log_error, 'errno'):
                            print(f"❌ MySQL Error Code: {payment_log_error.errno}")
                        if hasattr(payment_log_error, 'sqlstate'):
                            print(f"❌ SQL State: {payment_log_error.sqlstate}")
                        # payment_logs 저장 실패 시에도 구독은 유지
                        print(f"⚠️ payment_logs 저장 실패했지만 구독은 유지됨 (ID: {subscription_id})")
                        # payment_logs 오류는 무시하고 성공 응답
                        conn.commit()
                        return {
                            "success": True,
                            "message": f"{plan[1]} 요금제 구독이 완료되었습니다. (결제 로그 저장 실패)",
                            "payment_id": request.paymentKey,
                            "plan_id": request.plan_id
                        }
                    
                    print(f"🔄 커밋 시작...")
                    conn.commit()
                    print(f"✅ 커밋 완료")
                    
                    print(f"✅ DB 저장 완료 - 구독 ID: {subscription_id}")
                    print(f"🎯 응답 생성 시작...")
                    
                    print(f"📝 plan 전체 값: {plan}")
                    print(f"📝 plan 타입: {type(plan)}")
                    print(f"📝 plan 길이: {len(plan) if plan else 'None'}")
                    
                    if plan and len(plan) > 1:
                        print(f"📝 plan[1] 값: {plan[1]}")
                        print(f"📝 plan[1] 타입: {type(plan[1])}")
                    else:
                        print(f"❌ plan 데이터 부족: {plan}")
                    
                    print(f"📝 request.paymentKey 값: {request.paymentKey}")
                    print(f"📝 request.plan_id 값: {request.plan_id}")
                    
                    # 안전한 응답 생성 (plan 데이터 타입에 맞게 처리)
                    print(f"🔄 응답 생성 시작...")
                    
                    # plan 데이터에서 요금제 이름 추출 (dict 또는 tuple 모두 지원)
                    if isinstance(plan, dict):
                        plan_name = plan.get('name', '요금제')
                        print(f"✅ dict에서 plan_name 추출: {plan_name}")
                    elif plan and len(plan) > 1:
                        plan_name = str(plan[1]) if plan[1] else '요금제'
                        print(f"✅ tuple에서 plan_name 추출: {plan_name}")
                    else:
                        plan_name = '요금제'
                        print(f"⚠️ 기본 plan_name 사용: {plan_name}")
                    
                    response_data = {
                        "success": True,
                        "message": f"{plan_name} 요금제 구독이 완료되었습니다.",
                        "payment_id": request.paymentKey,
                        "plan_id": request.plan_id
                    }
                    
                    print(f"✅ response_data 생성 완료: {response_data}")
                    print(f"🔄 return 시작...")
                    return response_data
                    
                except Exception as e:
                    conn.rollback()
                    print(f"❌ DB 저장 오류: {e}")
                    print(f"❌ Error type: {type(e).__name__}")
                    if hasattr(e, 'args'):
                        print(f"❌ Error args: {e.args}")
                    if hasattr(e, 'errno'):
                        print(f"❌ MySQL Error Code: {e.errno}")
                    if hasattr(e, 'sqlstate'):
                        print(f"❌ SQL State: {e.sqlstate}")
                    import traceback
                    print(f"❌ Stack trace:\n{traceback.format_exc()}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"구독 정보 저장 중 오류가 발생했습니다: {str(e)} (Error Type: {type(e).__name__})"
                    )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 결제 완료 처리 오류: {e}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"결제 완료 처리 중 오류가 발생했습니다: {str(e)}"
        )

@router.get("/status/{order_id}")
async def get_payment_status(
    order_id: str,
    user=Depends(get_current_user_from_request)
):
    """결제 상태 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute("""
                        SELECT pl.status, pl.paid_at, pl.amount, p.name as plan_name
                        FROM payment_logs pl
                        JOIN user_subscriptions us ON pl.user_id = us.user_id
                        JOIN plans p ON us.plan_id = p.id
                        WHERE pl.payment_id = %s AND pl.user_id = %s
                    """, (order_id, user["id"]))
                    
                    payment_info = cursor.fetchone()
                    
                    if not payment_info:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="결제 정보를 찾을 수 없습니다."
                        )
                    
                    return {
                        "success": True,
                        "status": payment_info[0],
                        "processed_at": payment_info[1].isoformat() if payment_info[1] else None,
                        "amount": payment_info[2],
                        "plan_name": payment_info[3]
                    }
                    
                except Exception as e:
                    print(f"❌ DB 조회 오류: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"결제 상태 조회 중 오류가 발생했습니다: {str(e)}"
                    )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 결제 상태 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"결제 상태 조회 중 오류가 발생했습니다: {str(e)}"
        ) 