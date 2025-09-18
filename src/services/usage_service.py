from datetime import datetime, date
from src.config.database import get_db_connection
import logging

logger = logging.getLogger(__name__)


class UsageService:
    """사용자별 캡차 API 사용량 추적 서비스"""
    
    @staticmethod
    async def increment_captcha_usage(user_id: int):
        """캡차 API 사용 시 사용량 증가"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    today = date.today()
                    
                    # 오늘 날짜의 사용량 기록이 있는지 확인
                    cursor.execute("""
                        SELECT id FROM user_usage_tracking 
                        WHERE user_id = %s AND tracking_date = %s
                    """, (user_id, today))
                    
                    existing_record = cursor.fetchone()
                    
                    if existing_record:
                        # 기존 기록이 있으면 사용량 증가
                        cursor.execute("""
                            UPDATE user_usage_tracking 
                            SET 
                                per_minute_count = per_minute_count + 1,
                                per_day_count = per_day_count + 1,
                                per_month_count = per_month_count + 1,
                                last_updated = CURRENT_TIMESTAMP
                            WHERE user_id = %s AND tracking_date = %s
                        """, (user_id, today))
                    else:
                        # 새로운 기록 생성
                        cursor.execute("""
                            INSERT INTO user_usage_tracking 
                            (user_id, tracking_date, per_minute_count, per_day_count, per_month_count)
                            VALUES (%s, %s, 1, 1, 1)
                        """, (user_id, today))
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"사용량 증가 실패: {e}")
            return False
    
    @staticmethod
    async def get_user_usage(user_id: int):
        """사용자의 현재 사용량 조회"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    today = date.today()
                    
                    # 오늘 사용량 조회
                    cursor.execute("""
                        SELECT 
                            per_minute_count,
                            per_day_count,
                            per_month_count,
                            last_updated
                        FROM user_usage_tracking 
                        WHERE user_id = %s AND tracking_date = %s
                    """, (user_id, today))
                    
                    result = cursor.fetchone()
                    
                    if result:
                        return {
                            "perMinute": result.get("per_minute_count", 0),
                            "perDay": result.get("per_day_count", 0),
                            "perMonth": result.get("per_month_count", 0),
                            "lastUpdated": result.get("last_updated")
                        }
                    else:
                        return {
                            "perMinute": 0,
                            "perDay": 0,
                            "perMonth": 0,
                            "lastUpdated": None
                        }
                        
        except Exception as e:
            logger.error(f"사용량 조회 실패: {e}")
            return {
                "perMinute": 0,
                "perDay": 0,
                "perMonth": 0,
                "lastUpdated": None
            }
    
    @staticmethod
    async def reset_periodic_usage():
        """주기적 사용량 리셋 (스케줄러에서 실행)"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    now = datetime.now()
                    today = date.today()
                    
                    # 분당 리셋 (매분)
                    # 컬럼 존재 여부와 관계 없이 WHERE에서 참조하지 않도록 조건을 단순화
                    cursor.execute("""
                        UPDATE user_usage_tracking 
                        SET 
                            per_minute_count = 0,
                            per_minute_reset_time = %s
                        WHERE tracking_date = %s
                    """, (now, today))
                    
                    # 일일 리셋 (매일 자정) - 자정이 지났을 때만
                    if now.hour == 0 and now.minute == 0:
                        cursor.execute("""
                            UPDATE user_usage_tracking 
                            SET 
                                per_day_count = 0,
                                per_day_reset_time = %s
                            WHERE tracking_date = %s
                        """, (now, today))
                    
                    # 월간 리셋 (매월 1일) - 1일이 되었을 때만
                    if now.day == 1 and now.hour == 0 and now.minute == 0:
                        cursor.execute("""
                            UPDATE user_usage_tracking 
                            SET 
                                per_month_count = 0,
                                per_month_reset_time = %s
                            WHERE tracking_date = %s
                        """, (now, today))
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"사용량 리셋 실패: {e}")
            return False

# 싱글톤 인스턴스
usage_service = UsageService()
