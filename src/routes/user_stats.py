"""
사용자 통계 API 엔드포인트
사용자별 개인 통계 조회 (총 요청 수, 성공률, 평균 응답 시간)
"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["user-stats"])

class CaptchaTypeStats(BaseModel):
    captcha_type: str
    total_requests: int
    success_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time: float

class ApiKeyStats(BaseModel):
    api_key_id: str
    api_key_name: str
    total_requests: int
    success_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time: float
    captcha_types: List[CaptchaTypeStats]

class UserStatsResponse(BaseModel):
    success: bool
    data: Dict[str, Any]

def get_date_filter(period: str, table_name: str = "daily_user_api_stats") -> str:
    """기간에 따른 날짜 필터 조건 반환"""
    if table_name == "daily_user_api_stats":
        # daily_user_api_stats 테이블은 date 컬럼 사용
        if period == "today":
            return "date = CURDATE()"
        elif period == "week":
            return "date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
        elif period == "month":
            return "date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"
        else:
            return "date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"  # 기본값: 한달
    else:
        # api_request_logs 테이블은 created_at 컬럼 사용
        if period == "today":
            return f"DATE({table_name}.created_at) = CURDATE()"
        elif period == "week":
            return f"{table_name}.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        elif period == "month":
            return f"{table_name}.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
        else:
            return f"{table_name}.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"  # 기본값: 한달

@router.get("/user/stats/overview")
def get_user_stats_overview(
    request: Request,
    period: str = Query("month", description="통계 기간: today, week, month")
):
    """사용자 통계 개요 조회 (전체 합계)"""
    try:
        # 사용자 인증 확인
        current_user = get_current_user_from_request(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.get("id")
        logger.info(f"사용자 통계 조회 시작: 사용자 {user_id}, 기간 {period}")
        
        date_filter = get_date_filter(period)
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. 전체 통계 (모든 API 키 합계) - daily_user_api_stats 테이블 사용
                overview_query = f"""
                    SELECT 
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as success_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND {get_date_filter(period, "daily_user_api_stats")}
                """
                cursor.execute(overview_query, (user_id,))
                overview = cursor.fetchone()
                
                if not overview or overview['total_requests'] == 0:
                    return {
                        "success": True,
                        "data": {
                            "total_requests": 0,
                            "success_requests": 0,
                            "failed_requests": 0,
                            "success_rate": 0.0,
                            "avg_response_time": 0.0,
                            "period": period
                        }
                    }
                
                # 2. 캡차 타입별 통계 - daily_user_api_stats 테이블 사용
                type_query = f"""
                    SELECT 
                        COALESCE(api_type, 'unknown') as captcha_type,
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as success_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND {get_date_filter(period)}
                    GROUP BY api_type
                    ORDER BY total_requests DESC
                """
                cursor.execute(type_query, (user_id,))
                type_stats = cursor.fetchall()
                
                # 성공률 계산
                success_rate = (overview['success_requests'] / overview['total_requests'] * 100) if overview['total_requests'] > 0 else 0
                
                # 캡차 타입별 통계 포맷팅
                captcha_types = []
                for stat in type_stats:
                    type_success_rate = (stat['success_requests'] / stat['total_requests'] * 100) if stat['total_requests'] > 0 else 0
                    captcha_types.append({
                        "captcha_type": stat['captcha_type'],
                        "total_requests": stat['total_requests'],
                        "success_requests": stat['success_requests'],
                        "failed_requests": stat['failed_requests'],
                        "success_rate": round(type_success_rate, 2),
                        "avg_response_time": round(float(stat['avg_response_time'] or 0), 2)
                    })
                
                return {
                    "success": True,
                    "data": {
                        "total_requests": overview['total_requests'],
                        "success_requests": overview['success_requests'],
                        "failed_requests": overview['failed_requests'],
                        "success_rate": round(success_rate, 2),
                        "avg_response_time": round(float(overview['avg_response_time'] or 0), 2),
                        "captcha_types": captcha_types,
                        "period": period
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"통계 조회에 실패했습니다: {str(e)}")

@router.get("/user/stats/by-api-key")
def get_user_stats_by_api_key(
    request: Request,
    period: str = Query("month", description="통계 기간: today, week, month")
):
    """API 키별 상세 통계 조회"""
    try:
        # 사용자 인증 확인
        current_user = get_current_user_from_request(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.get("id")
        logger.info(f"API 키별 통계 조회 시작: 사용자 {user_id}, 기간 {period}")
        
        date_filter = get_date_filter(period)
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자의 API 키 목록 조회
                cursor.execute("""
                    SELECT key_id, name, is_active, created_at
                    FROM api_keys 
                    WHERE user_id = %s AND is_active = 1
                    ORDER BY created_at DESC
                """, (user_id,))
                api_keys = cursor.fetchall()
                
                if not api_keys:
                    return {
                        "success": True,
                        "data": {
                            "api_keys": [],
                            "period": period
                        }
                    }
                
                api_key_stats = []
                
                for api_key in api_keys:
                    key_id = api_key['key_id']
                    key_name = api_key['name']
                    
                    # API 키별 전체 통계 - daily_user_api_stats 테이블 사용
                    key_query = f"""
                        SELECT 
                            SUM(total_requests) as total_requests,
                            SUM(successful_requests) as success_requests,
                            SUM(failed_requests) as failed_requests,
                            AVG(avg_response_time) as avg_response_time
                        FROM daily_user_api_stats
                        WHERE api_key = %s AND user_id = %s AND {get_date_filter(period)}
                    """
                    cursor.execute(key_query, (key_id, user_id))
                    key_overview = cursor.fetchone()
                    
                    # API 키별 캡차 타입 통계 - daily_user_api_stats 테이블 사용
                    key_type_query = f"""
                        SELECT 
                            COALESCE(api_type, 'unknown') as captcha_type,
                            SUM(total_requests) as total_requests,
                            SUM(successful_requests) as success_requests,
                            SUM(failed_requests) as failed_requests,
                            AVG(avg_response_time) as avg_response_time
                        FROM daily_user_api_stats
                        WHERE api_key = %s AND user_id = %s AND {get_date_filter(period)}
                        GROUP BY api_type
                        ORDER BY total_requests DESC
                    """
                    cursor.execute(key_type_query, (key_id, user_id))
                    key_type_stats = cursor.fetchall()
                    
                    # 통계 계산
                    total_requests = key_overview['total_requests'] or 0
                    success_requests = key_overview['success_requests'] or 0
                    failed_requests = key_overview['failed_requests'] or 0
                    success_rate = (success_requests / total_requests * 100) if total_requests > 0 else 0
                    avg_response_time = float(key_overview['avg_response_time'] or 0)
                    
                    # 캡차 타입별 통계 포맷팅
                    captcha_types = []
                    for stat in key_type_stats:
                        type_success_rate = (stat['success_requests'] / stat['total_requests'] * 100) if stat['total_requests'] > 0 else 0
                        captcha_types.append({
                            "captcha_type": stat['captcha_type'],
                            "total_requests": stat['total_requests'],
                            "success_requests": stat['success_requests'],
                            "failed_requests": stat['failed_requests'],
                            "success_rate": round(type_success_rate, 2),
                            "avg_response_time": round(float(stat['avg_response_time'] or 0), 2)
                        })
                    
                    api_key_stats.append({
                        "api_key_id": key_id,
                        "api_key_name": key_name,
                        "total_requests": total_requests,
                        "success_requests": success_requests,
                        "failed_requests": failed_requests,
                        "success_rate": round(success_rate, 2),
                        "avg_response_time": round(avg_response_time, 2),
                        "captcha_types": captcha_types
                    })
                
                return {
                    "success": True,
                    "data": {
                        "api_keys": api_key_stats,
                        "period": period
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API 키별 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"API 키별 통계 조회에 실패했습니다: {str(e)}")

@router.get("/user/stats/time-series")
def get_user_stats_time_series(
    request: Request,
    period: str = Query("week", description="통계 기간: today, week, month"),
    api_key_id: Optional[str] = Query(None, description="특정 API 키 ID (선택사항)")
):
    """시계열 통계 데이터 조회 (차트용)"""
    try:
        # 사용자 인증 확인
        current_user = get_current_user_from_request(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.get("id")
        logger.info(f"시계열 통계 조회 시작: 사용자 {user_id}, 기간 {period}, API 키 {api_key_id}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # daily_user_api_stats 테이블을 사용하여 시계열 데이터 조회
                # 기간에 따른 그룹화 설정
                if period == "today":
                    # 오늘은 일별 데이터만 제공 (시간별 집계 없음)
                    date_format = "%Y-%m-%d"
                    date_filter = get_date_filter("today")
                    group_by = "date"
                elif period == "week":
                    date_format = "%Y-%m-%d"
                    date_filter = get_date_filter("week")
                    group_by = "date"
                else:  # month
                    date_format = "%Y-%m-%d"
                    date_filter = get_date_filter("month")
                    group_by = "date"
                
                # API 키 필터 추가
                api_key_filter = ""
                params = [user_id]
                if api_key_id:
                    api_key_filter = "AND api_key = %s"
                    params.append(api_key_id)
                
                time_series_query = f"""
                    SELECT 
                        DATE_FORMAT(date, '{date_format}') as time_label,
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as success_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND {date_filter} {api_key_filter}
                    GROUP BY {group_by}
                    ORDER BY {group_by}
                """
                
                cursor.execute(time_series_query, params)
                time_series_data = cursor.fetchall()
                
                # 데이터 포맷팅
                formatted_data = []
                for data in time_series_data:
                    success_rate = (data['success_requests'] / data['total_requests'] * 100) if data['total_requests'] > 0 else 0
                    formatted_data.append({
                        "time": data['time_label'],
                        "total_requests": data['total_requests'],
                        "success_requests": data['success_requests'],
                        "failed_requests": data['failed_requests'],
                        "success_rate": round(success_rate, 2),
                        "avg_response_time": round(float(data['avg_response_time'] or 0), 2)
                    })
                
                return {
                    "success": True,
                    "data": {
                        "time_series": formatted_data,
                        "period": period,
                        "api_key_id": api_key_id
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"시계열 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"시계열 통계 조회에 실패했습니다: {str(e)}")
