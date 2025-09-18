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
        # request_logs 테이블은 request_time 컬럼 사용
        if period == "today":
            return f"DATE({table_name}.request_time) = CURDATE()"
        elif period == "week":
            return f"{table_name}.request_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        elif period == "month":
            return f"{table_name}.request_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
        else:
            return f"{table_name}.request_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)"  # 기본값: 한달

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
                # 1. 전체 통계 (모든 API 키 합계) - request_logs 테이블에서 실시간 계산
                overview_query = f"""
                    SELECT 
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success_requests,
                        SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed_requests,
                        COALESCE(AVG(response_time), 0.0) as avg_response_time
                    FROM request_logs
                    WHERE user_id = %s AND user_id IS NOT NULL AND {get_date_filter(period, "request_logs")}
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
                            "peak_daily_requests": 0,
                            "peak_date": None,
                            "captcha_types": [],
                            "period": period
                        }
                    }
                
                # 2. 캡차 타입별 통계 - request_logs 테이블에서 실시간 계산
                # api_type이 pass인 경우는 handwriting으로 매핑하여 처리
                type_query = f"""
                    SELECT 
                        CASE 
                            WHEN api_type = 'handwriting' THEN 'handwriting'
                            WHEN api_type = 'abstract' THEN 'abstract'
                            WHEN api_type = 'imagecaptcha' THEN 'imagecaptcha'
                            ELSE 'unknown'
                        END as captcha_type,
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success_requests,
                        SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed_requests,
                        COALESCE(AVG(response_time), 0.0) as avg_response_time
                    FROM request_logs
                    WHERE user_id = %s AND user_id IS NOT NULL AND {get_date_filter(period, "request_logs")}
                    GROUP BY 
                        CASE 
                            WHEN api_type = 'handwriting' THEN 'handwriting'
                            WHEN api_type = 'abstract' THEN 'abstract'
                            WHEN api_type = 'imagecaptcha' THEN 'imagecaptcha'
                            ELSE 'unknown'
                        END
                    ORDER BY total_requests DESC
                """
                cursor.execute(type_query, (user_id,))
                type_stats = cursor.fetchall()
                
                # 성공률 계산
                success_rate = (overview['success_requests'] / overview['total_requests'] * 100) if overview['total_requests'] > 0 else 0
                
                # 3. 최고 일일 요청수 조회 - request_logs 테이블에서 실시간 계산
                date_filter_condition = get_date_filter(period, "request_logs")
                peak_query = f"""
                    SELECT 
                        DATE_FORMAT(request_time, '%%Y-%%m-%%d') as peak_date,
                        COUNT(*) as daily_total
                    FROM request_logs
                    WHERE user_id = %s AND user_id IS NOT NULL AND {date_filter_condition}
                    GROUP BY DATE(request_time)
                    ORDER BY daily_total DESC
                    LIMIT 1
                """
                cursor.execute(peak_query, (user_id,))
                peak_result = cursor.fetchone()
                
                peak_daily_requests = int(peak_result['daily_total'] or 0) if peak_result else 0
                peak_date = peak_result['peak_date'] if peak_result else None
                
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
                        "peak_daily_requests": peak_daily_requests,
                        "peak_date": peak_date,
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
    period: str = Query("month", description="통계 기간: today, week, month"),
    include_inactive_deleted: bool = Query(False, description="비활성+삭제 키 포함 여부")
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
                if include_inactive_deleted:
                    # 기간 내 활동한 모든 키(비활성/삭제 포함) - request_logs에서 조회
                    cursor.execute(f"""
                        SELECT 
                            DISTINCT rl.api_key AS key_id,
                            COALESCE(ak.name, rl.api_key) AS name,
                            COALESCE(ak.is_active, 0) AS is_active,
                            CASE WHEN ak.key_id IS NULL THEN 1 ELSE 0 END AS is_deleted
                        FROM request_logs rl
                        LEFT JOIN api_keys ak ON ak.key_id = rl.api_key
                        WHERE rl.user_id = %s AND rl.user_id IS NOT NULL AND {get_date_filter(period, "request_logs")}
                        ORDER BY name DESC
                    """, (user_id,))
                else:
                    # 활성 키만
                    cursor.execute("""
                        SELECT key_id, name, 1 AS is_active, 0 AS is_deleted
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
                    
                    # API 키별 전체 통계 - request_logs 테이블에서 실시간 계산
                    key_query = f"""
                        SELECT 
                            COUNT(*) as total_requests,
                            SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success_requests,
                            SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed_requests,
                            COALESCE(AVG(response_time), 0.0) as avg_response_time
                        FROM request_logs
                        WHERE api_key = %s AND user_id = %s AND user_id IS NOT NULL AND {get_date_filter(period, "request_logs")}
                    """
                    cursor.execute(key_query, (key_id, user_id))
                    key_overview = cursor.fetchone()
                    
                    # API 키별 캡차 타입 통계 - request_logs 테이블에서 실시간 계산
                    # api_type이 pass인 경우는 handwriting으로 매핑하여 처리
                    key_type_query = f"""
                        SELECT 
                            CASE 
                                WHEN api_type = 'handwriting' THEN 'handwriting'
                                WHEN api_type = 'abstract' THEN 'abstract'
                                WHEN api_type = 'imagecaptcha' THEN 'imagecaptcha'
                                ELSE 'unknown'
                            END as captcha_type,
                            COUNT(*) as total_requests,
                            SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success_requests,
                            SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed_requests,
                            COALESCE(AVG(response_time), 0.0) as avg_response_time
                        FROM request_logs
                        WHERE api_key = %s AND user_id = %s AND user_id IS NOT NULL AND {get_date_filter(period, "request_logs")}
                        GROUP BY 
                            CASE 
                                WHEN api_type = 'handwriting' THEN 'handwriting'
                                WHEN api_type = 'abstract' THEN 'abstract'
                                WHEN api_type = 'imagecaptcha' THEN 'imagecaptcha'
                                ELSE 'unknown'
                            END
                        ORDER BY total_requests DESC
                    """
                    cursor.execute(key_type_query, (key_id, user_id))
                    key_type_stats = cursor.fetchall()
                    
                    # 통계 계산 (안전한 타입 변환)
                    total_requests = int(key_overview['total_requests'] or 0)
                    success_requests = int(key_overview['success_requests'] or 0)
                    failed_requests = int(key_overview['failed_requests'] or 0)
                    success_rate = (success_requests / total_requests * 100) if total_requests > 0 else 0.0
                    avg_response_time = float(key_overview['avg_response_time'] or 0.0)
                    
                    # 캡차 타입별 통계 포맷팅 (안전한 타입 변환)
                    captcha_types = []
                    for stat in key_type_stats:
                        stat_total = int(stat['total_requests'] or 0)
                        stat_success = int(stat['success_requests'] or 0)
                        stat_failed = int(stat['failed_requests'] or 0)
                        type_success_rate = (stat_success / stat_total * 100) if stat_total > 0 else 0.0
                        captcha_types.append({
                            "captcha_type": stat['captcha_type'],
                            "total_requests": stat_total,
                            "success_requests": stat_success,
                            "failed_requests": stat_failed,
                            "success_rate": round(type_success_rate, 2),
                            "avg_response_time": round(float(stat['avg_response_time'] or 0.0), 2)
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
                # request_logs 테이블을 사용하여 시계열 데이터 조회
                # 기간에 따른 그룹화 설정
                if period == "today":
                    # 오늘은 시간별 집계
                    date_format = "%H:00"
                    date_filter = get_date_filter("today", "request_logs")
                    group_by = "HOUR(request_time)"
                elif period == "week":
                    # 주간은 일별 집계
                    date_format = "%Y-%m-%d"
                    date_filter = get_date_filter("week", "request_logs")
                    group_by = "DATE(request_time)"
                else:  # month
                    # 월간은 일별 집계
                    date_format = "%Y-%m-%d"
                    date_filter = get_date_filter("month", "request_logs")
                    group_by = "DATE(request_time)"
                
                # API 키 필터 추가
                api_key_filter = ""
                params = [user_id]
                if api_key_id:
                    api_key_filter = "AND api_key = %s"
                    params.append(api_key_id)
                
                time_series_query = f"""
                    SELECT 
                        DATE_FORMAT(request_time, '{date_format}') as time_label,
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success_requests,
                        SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed_requests,
                        COALESCE(AVG(response_time), 0.0) as avg_response_time
                    FROM request_logs
                    WHERE user_id = %s AND user_id IS NOT NULL AND {date_filter} {api_key_filter}
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

@router.get("/user/stats/hourly-chart")
def get_user_hourly_chart_data(
    request: Request,
    period: str = Query("today", description="통계 기간: today, week, month")
):
    """시간별/일별 차트 데이터 조회"""
    try:
        # 사용자 인증 확인
        current_user = get_current_user_from_request(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.get("id")
        logger.info(f"시간별 차트 데이터 조회 시작: 사용자 {user_id}, 기간 {period}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if period == "today":
                    # 오늘 시간별 데이터 (0~23시, 2시간 단위로 집계)
                    chart_query = """
                        SELECT 
                            FLOOR(HOUR(arl.created_at) / 2) * 2 as hour_group,
                            COUNT(*) as total_requests,
                            COALESCE(SUM(CASE WHEN arl.status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END), 0) as success_requests,
                            COALESCE(SUM(CASE WHEN arl.status_code >= 400 THEN 1 ELSE 0 END), 0) as failed_requests
                        FROM api_request_logs arl
                        JOIN api_keys ak ON arl.api_key = ak.key_id
                        WHERE ak.user_id = %s AND DATE(arl.created_at) = CURDATE()
                        GROUP BY hour_group
                        ORDER BY hour_group
                    """
                    cursor.execute(chart_query, (user_id,))
                    raw_data = cursor.fetchall()
                    
                    # 0~23시 데이터를 2시간 단위로 생성 (00, 02, 04, ..., 22)
                    chart_data = []
                    data_dict = {int(row['hour_group']): row for row in raw_data}
                    
                    for hour in range(0, 24, 2):
                        if hour in data_dict:
                            row = data_dict[hour]
                            chart_data.append({
                                "time": f"{hour:02d}시",
                                "requests": int(row['total_requests']),
                                "success": int(row['success_requests']),
                                "failed": int(row['failed_requests'])
                            })
                        else:
                            chart_data.append({
                                "time": f"{hour:02d}시",
                                "requests": 0,
                                "success": 0,
                                "failed": 0
                            })
                    
                else:
                    # week/month는 일별 데이터
                    date_filter = get_date_filter(period, "daily_user_api_stats")
                    chart_query = f"""
                        SELECT 
                            DATE_FORMAT(date, '%%m/%%d') as time_label,
                            COALESCE(SUM(total_requests), 0) as total_requests,
                            COALESCE(SUM(successful_requests), 0) as success_requests,
                            COALESCE(SUM(failed_requests), 0) as failed_requests
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND {date_filter}
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(chart_query, (user_id,))
                    raw_data = cursor.fetchall()
                    
                    chart_data = []
                    for row in raw_data:
                        chart_data.append({
                            "time": row['time_label'],
                            "requests": int(row['total_requests']),
                            "success": int(row['success_requests']),
                            "failed": int(row['failed_requests'])
                        })
                
                return {
                    "success": True,
                    "data": {
                        "chart_data": chart_data,
                        "period": period
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"시간별 차트 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"차트 데이터 조회에 실패했습니다: {str(e)}")
