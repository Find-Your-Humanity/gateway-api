import asyncio
import time
import logging
from datetime import date, datetime, timedelta
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request

logger = logging.getLogger(__name__)

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

class ApiUsageTracker:
    """API 키별 사용량을 실시간으로 추적하는 클래스"""
    
    @staticmethod
    def track_api_key_usage(api_key: str, user_id: int = None):
        """API 키 사용량을 추적하고 업데이트"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    today = datetime.now().date()
                    
                    # 1. api_keys 테이블의 usage_count 업데이트 (안전하게)
                    try:
                        cursor.execute("""
                            UPDATE api_keys 
                            SET 
                                usage_count = COALESCE(usage_count, 0) + 1,
                                last_used_at = NOW()
                            WHERE key_id = %s
                        """, (api_key,))
                    except Exception as e:
                        logger.warning(f"api_keys 테이블 업데이트 실패: {e}")
                    
                    # 2. user_usage_tracking 테이블 업데이트 (사용자별, 안전하게)
                    if user_id:
                        try:
                            # 오늘 데이터가 있는지 확인
                            cursor.execute("""
                                SELECT id, per_minute_count, per_day_count, per_month_count
                                FROM user_usage_tracking
                                WHERE user_id = %s AND tracking_date = %s
                            """, (user_id, today))
                            
                            existing_record = cursor.fetchone()
                            
                            if existing_record:
                                # 기존 기록 업데이트
                                cursor.execute("""
                                    UPDATE user_usage_tracking
                                    SET 
                                        per_minute_count = COALESCE(per_minute_count, 0) + 1,
                                        per_day_count = COALESCE(per_day_count, 0) + 1,
                                        per_month_count = COALESCE(per_month_count, 0) + 1,
                                        last_updated = NOW()
                                    WHERE id = %s
                                """, (existing_record['id'],))
                            else:
                                # 새 기록 생성
                                cursor.execute("""
                                    INSERT INTO user_usage_tracking
                                    (user_id, tracking_date, per_minute_count, per_day_count, per_month_count)
                                    VALUES (%s, %s, 1, 1, 1)
                                """, (user_id, today))
                        except Exception as e:
                            logger.warning(f"user_usage_tracking 테이블 업데이트 실패: {e}")
                    
                    # 3. user_subscriptions 테이블의 current_usage 업데이트 (가장 최근 활성 구독만)
                    if user_id:
                        try:
                            cursor.execute("""
                                UPDATE user_subscriptions 
                                SET current_usage = COALESCE(current_usage, 0) + 1
                                WHERE user_id = %s AND status = 'active'
                                ORDER BY created_at DESC
                                LIMIT 1
                            """, (user_id,))
                        except Exception as e:
                            logger.warning(f"user_subscriptions 테이블 업데이트 실패: {e}")
                    
                    conn.commit()
                    logger.info(f"API 키 {api_key} 사용량 추적 완료")
                    
        except Exception as e:
            logger.error(f"API 키 사용량 추적 실패: {e}")
    
    @staticmethod
    def get_api_key_usage_stats(api_key: str):
        """API 키별 사용량 통계 조회"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. API 키 기본 정보 조회
                    cursor.execute("""
                        SELECT 
                            ak.key_id,
                            ak.name,
                            ak.usage_count,
                            ak.last_used_at,
                            u.email as user_email,
                            u.username
                        FROM api_keys ak
                        LEFT JOIN users u ON ak.user_id = u.id
                        WHERE ak.key_id = %s
                    """, (api_key,))
                    
                    api_key_info = cursor.fetchone()
                    if not api_key_info:
                        return None
                    
                    # 2. 요청 통계 조회 (별도 쿼리로 분리)
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_requests,
                            COUNT(CASE WHEN status_code = 200 THEN 1 END) as success_requests,
                            COUNT(CASE WHEN status_code != 200 THEN 1 END) as failed_requests,
                            ROUND(AVG(response_time), 2) as avg_response_time
                        FROM request_logs 
                        WHERE api_key = %s
                        AND request_time >= CURDATE() - INTERVAL 30 DAY
                    """, (api_key,))
                    
                    stats_info = cursor.fetchone()
                    
                    # 3. 결과 합치기
                    if stats_info:
                        return {
                            'key_id': api_key_info['key_id'],
                            'name': api_key_info['name'],
                            'usage_count': api_key_info['usage_count'],
                            'last_used_at': api_key_info['last_used_at'],
                            'user_email': api_key_info['user_email'],
                            'username': api_key_info['username'],
                            'total_requests': stats_info['total_requests'],
                            'success_requests': stats_info['success_requests'],
                            'failed_requests': stats_info['failed_requests'],
                            'avg_response_time': stats_info['avg_response_time']
                        }
                    else:
                        # 통계가 없는 경우 기본값으로 반환
                        return {
                            'key_id': api_key_info['key_id'],
                            'name': api_key_info['name'],
                            'usage_count': api_key_info['usage_count'],
                            'last_used_at': api_key_info['last_used_at'],
                            'user_email': api_key_info['user_email'],
                            'username': api_key_info['username'],
                            'total_requests': 0,
                            'success_requests': 0,
                            'failed_requests': 0,
                            'avg_response_time': 0
                        }
                    
        except Exception as e:
            logger.error(f"API 키 사용량 통계 조회 실패: {e}")
            return None
