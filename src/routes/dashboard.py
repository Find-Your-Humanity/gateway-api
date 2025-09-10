from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import Literal, Optional, List, Dict, Any
from datetime import date, timedelta, datetime
import pymysql
from src.config.database import get_db_connection, cleanup_duplicate_request_statistics
from src.routes.auth import get_current_user_from_request
from src.middleware.usage_tracking import ApiUsageTracker
import logging

logger = logging.getLogger(__name__)

# 모듈 내 print 호출을 로거로 매핑합니다.
# 규칙: '❌' 또는 '오류' 또는 'error' 포함 시 error, '⚠️' 포함 시 warning, 그 외 info

def _dashboard_print(*args, sep=" ", end="\n"):
    try:
        msg = sep.join(str(a) for a in args)
    except Exception:
        msg = " ".join(map(str, args))
    low = msg.lower()
    if ("❌" in msg) or ("오류" in msg) or ("error" in low):
        logger.error(msg)
    elif "⚠️" in msg:
        logger.warning(msg)
    else:
        logger.info(msg)

print = _dashboard_print

router = APIRouter(prefix="/api", tags=["dashboard"])


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def require_auth(request: Request):
    """인증이 필요한 엔드포인트에서 사용할 의존성"""
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return user


@router.get("/dashboard/analytics")
def get_dashboard_analytics(request: Request, current_user = Depends(require_auth)):
    """대시보드 요약 분석 데이터 (실데이터) - 새로운 구조로 변경.
    - plan_info, today_stats, captcha_stats, level_stats 구조 사용
    - daily_user_api_stats 테이블 기반으로 사용자별 데이터 제공
    """
    user_id = current_user['id']
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 1. 사용자의 현재 플랜 정보 조회
                cursor.execute("""
                    SELECT 
                        u.id as user_id,
                        u.email,
                        p.id as plan_id,
                        p.name as plan_name,
                        p.display_name,
                        p.monthly_request_limit,
                        p.rate_limit_per_minute,
                        us.current_usage,
                        us.last_reset_at
                    FROM users u
                    LEFT JOIN user_subscriptions us ON u.id = us.user_id
                    LEFT JOIN plans p ON us.plan_id = p.id
                    WHERE u.id = %s AND us.status = 'active'
                """, (user_id,))
                
                plan_info = cursor.fetchone()
                if not plan_info:
                    raise HTTPException(status_code=404, detail="사용자 플랜 정보를 찾을 수 없습니다")
                
                # 2. 이번 달 API 사용량 조회 (캡차 타입별) - 월간 구독 서비스에 맞게 변경
                today = datetime.now().date()
                month_start = today.replace(day=1)
                cursor.execute("""
                    SELECT 
                        api_type,
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as successful_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND date >= %s
                    GROUP BY api_type
                """, (user_id, month_start))
                
                monthly_stats_by_type = cursor.fetchall()
                
                # 3. 이번 달 총 사용량 조회
                cursor.execute("""
                    SELECT 
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as successful_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND date >= %s
                """, (user_id, month_start))
                
                month_stats = cursor.fetchone()
                
                # 4. 캡차 타입별 사용량 계산
                captcha_stats = {
                    'image': 0,
                    'handwriting': 0,
                    'abstract': 0,
                    'pass': 0
                }
                
                total_requests = 0
                for stat in monthly_stats_by_type:
                    api_type = stat['api_type']
                    requests = stat['total_requests'] or 0
                    total_requests += requests
                    
                    if api_type == 'imagecaptcha':
                        captcha_stats['image'] = requests
                    elif api_type == 'handwriting':
                        captcha_stats['handwriting'] = requests
                    elif api_type == 'abstract':
                        captcha_stats['abstract'] = requests
                
                # Pass는 총 사용량에서 다른 캡차 타입을 뺀 값
                captcha_stats['pass'] = max(0, total_requests - captcha_stats['image'] - captcha_stats['handwriting'] - captcha_stats['abstract'])
                
                # 5. Credit 사용량 계산
                monthly_limit = plan_info['monthly_request_limit'] or 0
                current_usage = month_stats['total_requests'] or 0
                credit_usage_percentage = (current_usage / monthly_limit * 100) if monthly_limit > 0 else 0
                
                # 6. 캡차 레벨별 사용량 계산 (퍼센테이지)
                total_captcha_usage = sum(captcha_stats.values())
                level_stats = {
                    'level_0': (captcha_stats['pass'] / total_captcha_usage * 100) if total_captcha_usage > 0 else 0,
                    'level_1': (captcha_stats['image'] / total_captcha_usage * 100) if total_captcha_usage > 0 else 0,
                    'level_2': (captcha_stats['handwriting'] / total_captcha_usage * 100) if total_captcha_usage > 0 else 0,
                    'level_3': (captcha_stats['abstract'] / total_captcha_usage * 100) if total_captcha_usage > 0 else 0,
                }
                
                return {
                    "success": True,
                    "data": {
                        "plan_info": {
                            "plan_name": plan_info['display_name'] or plan_info['plan_name'],
                            "monthly_limit": monthly_limit,
                            "current_usage": current_usage,
                            "usage_percentage": round(credit_usage_percentage, 1)
                        },
                        "monthly_stats": {
                            "total_requests": total_requests,
                            "successful_requests": sum(stat['successful_requests'] or 0 for stat in monthly_stats_by_type),
                            "failed_requests": sum(stat['failed_requests'] or 0 for stat in monthly_stats_by_type),
                            "success_rate": round((sum(stat['successful_requests'] or 0 for stat in monthly_stats_by_type) / total_requests * 100), 1) if total_requests > 0 else 0,
                            "avg_response_time": round(sum(stat['avg_response_time'] or 0 for stat in monthly_stats_by_type) / len(monthly_stats_by_type), 2) if monthly_stats_by_type else 0
                        },
                        "captcha_stats": captcha_stats,
                        "level_stats": level_stats
                    }
                }
                
    except Exception as e:
        print(f"대시보드 분석 데이터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="대시보드 데이터 조회에 실패했습니다")


@router.get("/dashboard/stats")
def get_dashboard_stats(
    request: Request,
    period: Literal["daily", "weekly", "monthly"] = Query("daily"),
    current_user = Depends(require_auth)
):
    """대시보드 통계 데이터를 반환합니다."""
    user_id = current_user['id']
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 기간별 데이터 조회
                if period == "daily":
                    # 최근 7일 데이터
                    start_date = datetime.now().date() - timedelta(days=6)
                    cursor.execute("""
                        SELECT 
                            date,
                            SUM(total_requests) as total_requests,
                            SUM(successful_requests) as successful_requests,
                            SUM(failed_requests) as failed_requests,
                            AVG(avg_response_time) as avg_response_time
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s
                        GROUP BY date
                        ORDER BY date
                    """, (user_id, start_date))
                elif period == "weekly":
                    # 최근 4주 데이터
                    start_date = datetime.now().date() - timedelta(weeks=3)
                    cursor.execute("""
                        SELECT 
                            YEARWEEK(date) as week,
                            SUM(total_requests) as total_requests,
                            SUM(successful_requests) as successful_requests,
                            SUM(failed_requests) as failed_requests,
                            AVG(avg_response_time) as avg_response_time
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s
                        GROUP BY YEARWEEK(date)
                        ORDER BY week
                    """, (user_id, start_date))
                else:  # monthly
                    # 최근 12개월 데이터
                    start_date = datetime.now().date() - timedelta(days=365)
                    cursor.execute("""
                        SELECT 
                            DATE_FORMAT(date, '%%Y-%%m') as month,
                            SUM(total_requests) as total_requests,
                            SUM(successful_requests) as successful_requests,
                            SUM(failed_requests) as failed_requests,
                            AVG(avg_response_time) as avg_response_time
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s
                        GROUP BY DATE_FORMAT(date, '%%Y-%%m')
                        ORDER BY month
                    """, (user_id, start_date))
                
                stats_data = cursor.fetchall()
                
                return {
                    "success": True,
                    "data": stats_data
                }
                
    except Exception as e:
        print(f"대시보드 통계 데이터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="대시보드 통계 데이터 조회에 실패했습니다")
