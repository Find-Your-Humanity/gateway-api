from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from pydantic import BaseModel
import httpx
import base64
import os
from datetime import datetime
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

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
                        (user_id, plan_id, start_date, end_date, status, amount, currency, payment_method)
                        VALUES (%s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 1 MONTH), 'active', %s, 'KRW', 'card')
                    """, (user["id"], request.plan_id, request.amount))

                    subscription_id = cursor.lastrowid

                    # payment_logs에 결제 기록 저장
                    cursor.execute("""
                        INSERT INTO payment_logs (user_id, plan_id, paid_at, amount, payment_method, payment_id, status)
                        VALUES (%s, %s, NOW(), %s, 'card', %s, 'completed')
                    """, (user["id"], request.plan_id, request.amount, request.orderId or request.paymentKey))
                    
                    conn.commit()
                    
                    print(f"✅ DB 저장 완료 - 구독 ID: {subscription_id}")
                    
                    return {
                        "success": True,
                        "message": f"{plan[1]} 요금제 구독이 완료되었습니다.",
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
                    
                    # 중복 결제 처리 방지
                    cursor.execute("""
                        SELECT id FROM payments WHERE payment_id = %s AND user_id = %s
                    """, (request.paymentKey, user["id"]))
                    
                    existing_payment = cursor.fetchone()
                    if existing_payment:
                        return {
                            "success": True,
                            "message": f"{plan[1]} 요금제 구독이 이미 완료되었습니다.",
                            "payment_id": request.paymentKey,
                            "plan_id": request.plan_id
                        }
                    
                    # users.plan_id 업데이트
                    cursor.execute("""
                        UPDATE users SET plan_id = %s WHERE id = %s
                    """, (request.plan_id, user["id"]))
                    
                    # subscriptions 테이블에 구독 정보 저장
                    cursor.execute("""
                        INSERT INTO subscriptions (user_id, plan_id, started_at, amount, payment_method, status)
                        VALUES (%s, %s, NOW(), %s, 'card', 'active')
                    """, (user["id"], request.plan_id, request.amount))
                    
                    subscription_id = cursor.lastrowid
                    
                    # payments 테이블에 결제 기록 저장
                    cursor.execute("""
                        INSERT INTO payments (subscription_id, user_id, payment_id, amount, currency, 
                                           payment_method, payment_gateway, status, processed_at, gateway_response)
                        VALUES (%s, %s, %s, %s, 'KRW', 'card', 'toss', 'completed', NOW(), %s)
                    """, (subscription_id, user["id"], request.paymentKey, request.amount, 
                          '{"status": "completed", "gateway": "toss"}'))
                    
                    conn.commit()
                    
                    print(f"✅ DB 저장 완료 - 구독 ID: {subscription_id}")
                    
                    return {
                        "success": True,
                        "message": f"{plan[1]} 요금제 구독이 완료되었습니다.",
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT p.status, p.processed_at, p.amount, pl.name as plan_name
                FROM payments p
                JOIN subscriptions s ON p.subscription_id = s.id
                JOIN plans pl ON s.plan_id = pl.id
                WHERE p.payment_id = %s AND p.user_id = %s
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
            
        finally:
            cursor.close()
            conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 결제 상태 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"결제 상태 조회 중 오류가 발생했습니다: {str(e)}"
        ) 