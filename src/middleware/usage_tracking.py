import asyncio
from datetime import date
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """API 호출 시 사용량을 자동으로 추적하는 미들웨어"""
    
    async def dispatch(self, request: Request, call_next):
        # 캡차 API 호출만 추적 (토큰 사용량이 있는 API)
        if not request.url.path.startswith('/api/captcha'):
            response = await call_next(request)
            return response
        
        # 사용자 정보 가져오기
        user = None
        try:
            user = await get_current_user_from_request(request)
        except:
            # 인증되지 않은 사용자는 추적하지 않음
            response = await call_next(request)
            return response
        
        if not user:
            response = await call_next(request)
            return response
        
        # 현재 사용자의 플랜 정보 가져오기
        current_plan = await self._get_current_plan(user["id"])
        if not current_plan:
            response = await call_next(request)
            return response
        
        # 요청 처리
        response = await call_next(request)
        
        # 성공적인 응답인 경우에만 사용량 추적
        if response.status_code == 200:
            # 비동기로 사용량 업데이트 (응답 지연 방지)
            asyncio.create_task(
                self._update_usage_tracking(
                    user["id"], 
                    current_plan["id"], 
                    current_plan["request_limit"]
                )
            )
        
        return response
    
    async def _get_current_plan(self, user_id: int):
        """현재 사용자의 활성 플랜 조회"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT p.id, p.request_limit
                FROM user_subscriptions us
                JOIN plans p ON us.plan_id = p.id
                WHERE us.user_id = %s AND us.status = 'active'
                ORDER BY us.created_at DESC
                LIMIT 1
            """, (user_id,))
            
            result = cursor.fetchone()
            if result:
                return {"id": result[0], "request_limit": result[1]}
            
            # 구독이 없으면 Free 플랜 반환
            cursor.execute("SELECT id, request_limit FROM plans WHERE name = 'Free'")
            free_plan = cursor.fetchone()
            if free_plan:
                return {"id": free_plan[0], "request_limit": free_plan[1]}
            
            return None
        finally:
            cursor.close()
            conn.close()
    
    async def _update_usage_tracking(self, user_id: int, plan_id: int, request_limit: int):
        """사용량 추적 업데이트"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            today = date.today()
            
            # 오늘 날짜의 사용량 레코드 확인
            cursor.execute("""
                SELECT id, tokens_used, api_calls
                FROM usage_tracking
                WHERE user_id = %s AND date = %s
            """, (user_id, today))
            
            existing_record = cursor.fetchone()
            
            # 평균 토큰 사용량 (실제로는 API 응답에서 계산해야 함)
            estimated_tokens = 20  # 기본 추정값
            
            if existing_record:
                # 기존 레코드 업데이트
                new_tokens_used = existing_record[1] + estimated_tokens
                new_api_calls = existing_record[2] + 1
                
                # 초과 사용량 계산
                overage_tokens = max(0, new_tokens_used - request_limit)
                overage_cost = (overage_tokens / 1000) * 2.0  # 1,000 토큰당 ₩2.0
                
                cursor.execute("""
                    UPDATE usage_tracking
                    SET tokens_used = %s, api_calls = %s, 
                        overage_tokens = %s, overage_cost = %s
                    WHERE id = %s
                """, (new_tokens_used, new_api_calls, overage_tokens, overage_cost, existing_record[0]))
            else:
                # 새 레코드 생성
                overage_tokens = max(0, estimated_tokens - request_limit)
                overage_cost = (overage_tokens / 1000) * 2.0
                
                cursor.execute("""
                    INSERT INTO usage_tracking 
                    (user_id, plan_id, date, tokens_used, api_calls, overage_tokens, overage_cost)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, plan_id, today, estimated_tokens, 1, overage_tokens, overage_cost))
            
            conn.commit()
        except Exception as e:
            print(f"Usage tracking error: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
