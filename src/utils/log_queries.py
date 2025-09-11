"""
통합 로그 조회를 위한 공통 함수들
request_logs와 api_request_logs 테이블을 통합하여 조회하는 유틸리티 함수들
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_combined_logs_query(
    time_filter: str = "NOW() - INTERVAL 1 HOUR",
    additional_where: str = "",
    select_fields: str = "*",
    order_by: str = "created_at DESC",
    limit: Optional[int] = None
) -> str:
    """
    두 로그 테이블을 통합하는 기본 쿼리 생성
    
    Args:
        time_filter: 시간 필터 조건 (예: "NOW() - INTERVAL 1 HOUR")
        additional_where: 추가 WHERE 조건
        select_fields: SELECT할 필드들
        order_by: 정렬 조건
        limit: 결과 제한 수
    
    Returns:
        통합 쿼리 문자열
    """
    where_clause = f"WHERE created_at >= {time_filter}"
    if additional_where:
        where_clause += f" AND {additional_where}"
    
    order_limit = f"ORDER BY {order_by}"
    if limit:
        order_limit += f" LIMIT {limit}"
    
    query = f"""
        SELECT {select_fields}
        FROM (
            SELECT {select_fields} FROM request_logs {where_clause}
            UNION ALL
            SELECT {select_fields} FROM api_request_logs {where_clause}
        ) as combined_logs
        {order_limit}
    """
    
    return query

def get_api_status_query(time_filter: str = "NOW() - INTERVAL 1 HOUR") -> str:
    """API 상태 조회 쿼리"""
    return f"""
        SELECT 
            path as endpoint,
            COUNT(*) as total_requests,
            COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0) as success_count,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_count,
            COALESCE(AVG(response_time), 0) as avg_response_time,
            MAX(request_time) as last_request_time
        FROM (
            SELECT CAST(path AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as path, status_code, response_time, request_time FROM request_logs 
            WHERE request_time >= {time_filter}
            UNION ALL
            SELECT CAST(path AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as path, status_code, response_time, created_at as request_time FROM api_request_logs 
            WHERE created_at >= {time_filter}
        ) as combined_logs
        GROUP BY path
        ORDER BY total_requests DESC
    """

def get_response_time_query(
    time_filter: str = "NOW() - INTERVAL 1 HOUR",
    time_bucket: str = "5분",
    limit: int = 12
) -> str:
    """응답 시간 분포 조회 쿼리"""
    if time_bucket == "5분":
        date_format = "DATE_FORMAT(request_time, '%Y-%m-%d %H:%i')"
    elif time_bucket == "1분":
        date_format = "DATE_FORMAT(request_time, '%Y-%m-%d %H:%i')"
    else:
        date_format = "DATE_FORMAT(request_time, '%Y-%m-%d %H:%i')"
    
    return f"""
        SELECT 
            {date_format} as time_bucket,
            COALESCE(AVG(response_time), 0) as avg_response_time,
            COALESCE(MAX(response_time), 0) as max_response_time,
            COALESCE(MIN(response_time), 0) as min_response_time,
            COUNT(*) as request_count
        FROM (
            SELECT response_time, request_time FROM request_logs 
            WHERE request_time >= {time_filter}
            UNION ALL
            SELECT response_time, created_at as request_time FROM api_request_logs 
            WHERE created_at >= {time_filter}
        ) as combined_logs
        GROUP BY time_bucket
        ORDER BY time_bucket DESC
        LIMIT {limit}
    """

def get_error_rate_query(
    time_filter: str = "NOW() - INTERVAL 1 HOUR",
    time_bucket: str = "5분",
    limit: int = 12
) -> str:
    """에러율 조회 쿼리"""
    if time_bucket == "5분":
        date_format = "DATE_FORMAT(request_time, '%Y-%m-%d %H:%i')"
    elif time_bucket == "1분":
        date_format = "DATE_FORMAT(request_time, '%Y-%m-%d %H:%i')"
    else:
        date_format = "DATE_FORMAT(request_time, '%Y-%m-%d %H:%i')"
    
    return f"""
        SELECT 
            {date_format} as time_bucket,
            COUNT(*) as total_requests,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_count
        FROM (
            SELECT status_code, request_time FROM request_logs 
            WHERE request_time >= {time_filter}
            UNION ALL
            SELECT status_code, created_at as request_time FROM api_request_logs 
            WHERE created_at >= {time_filter}
        ) as combined_logs
        GROUP BY time_bucket
        ORDER BY time_bucket DESC
        LIMIT {limit}
    """

def get_tps_query(
    time_filter: str = "NOW() - INTERVAL 1 HOUR",
    limit: int = 60
) -> str:
    """TPS (Transactions Per Second) 조회 쿼리"""
    return f"""
        SELECT 
            DATE_FORMAT(request_time, '%Y-%m-%d %H:%i') as time_bucket,
            COUNT(*) as request_count
        FROM (
            SELECT request_time FROM request_logs 
            WHERE request_time >= {time_filter}
            UNION ALL
            SELECT created_at as request_time FROM api_request_logs 
            WHERE created_at >= {time_filter}
        ) as combined_logs
        GROUP BY time_bucket
        ORDER BY time_bucket DESC
        LIMIT {limit}
    """

def get_system_summary_query(time_filter: str = "NOW() - INTERVAL 1 HOUR") -> str:
    """시스템 요약 조회 쿼리"""
    return f"""
        SELECT 
            COUNT(*) as total_requests_1h,
            COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0) as success_requests_1h,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_requests_1h,
            COALESCE(AVG(response_time), 0) as avg_response_time_1h,
            COUNT(DISTINCT user_id) as unique_users_1h
        FROM (
            SELECT status_code, response_time, user_id FROM request_logs 
            WHERE request_time >= {time_filter}
            UNION ALL
            SELECT status_code, response_time, user_id FROM api_request_logs 
            WHERE created_at >= {time_filter}
        ) as combined_logs
    """

def get_user_usage_query(
    user_id: int,
    time_filter: str = "NOW() - INTERVAL 30 DAY",
    additional_where: str = ""
) -> str:
    """사용자별 사용량 조회 쿼리"""
    where_clause = f"WHERE created_at >= {time_filter} AND user_id = {user_id}"
    if additional_where:
        where_clause += f" AND {additional_where}"
    
    return f"""
        SELECT 
            path as endpoint,
            COUNT(*) as total_requests,
            COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0) as success_count,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_count,
            COALESCE(AVG(response_time), 0) as avg_response_time,
            DATE(created_at) as request_date
        FROM (
            SELECT path, status_code, response_time, created_at, user_id FROM request_logs 
            {where_clause}
            UNION ALL
            SELECT path, status_code, response_time, created_at, user_id FROM api_request_logs 
            {where_clause}
        ) as combined_logs
        GROUP BY path, DATE(created_at)
        ORDER BY request_date DESC, total_requests DESC
    """

def get_endpoint_usage_query(
    time_filter: str = "NOW() - INTERVAL 7 DAY",
    limit: int = 20
) -> str:
    """엔드포인트별 사용량 조회 쿼리"""
    return f"""
        SELECT 
            path as endpoint,
            COUNT(*) as total_requests,
            COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0) as success_count,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_count,
            COALESCE(AVG(response_time), 0) as avg_response_time,
            COUNT(DISTINCT user_id) as unique_users
        FROM (
            SELECT path, status_code, response_time, user_id FROM request_logs 
            WHERE created_at >= {time_filter}
            UNION ALL
            SELECT path, status_code, response_time, user_id FROM api_request_logs 
            WHERE created_at >= {time_filter}
        ) as combined_logs
        GROUP BY path
        ORDER BY total_requests DESC
        LIMIT {limit}
    """

# 시간 필터 헬퍼 함수들
def get_time_filter(hours: int = 1) -> str:
    """시간 필터 생성"""
    return f"NOW() - INTERVAL {hours} HOUR"

def get_time_filter_days(days: int = 1) -> str:
    """일 단위 시간 필터 생성"""
    return f"NOW() - INTERVAL {days} DAY"

def get_time_filter_weeks(weeks: int = 1) -> str:
    """주 단위 시간 필터 생성"""
    return f"NOW() - INTERVAL {weeks} WEEK"

def get_time_filter_months(months: int = 1) -> str:
    """월 단위 시간 필터 생성"""
    return f"NOW() - INTERVAL {months} MONTH"
