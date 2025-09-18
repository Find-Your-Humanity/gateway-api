from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import Literal, Optional, List, Dict, Any
from datetime import date, timedelta, datetime
import pymysql
from src.config.database import get_db_connection, cleanup_duplicate_request_statistics
from src.routes.auth import get_current_user_from_request
from src.middleware.usage_tracking import ApiUsageTracker
from src.utils.log_queries import (
    get_user_usage_query,
    get_endpoint_usage_query,
    get_time_filter_days,
    get_time_filter_weeks,
    get_time_filter_months
)
import logging

logger = logging.getLogger(__name__)


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
                    LEFT JOIN user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
                    LEFT JOIN plans p ON (
                        (us.plan_id IS NOT NULL AND p.id = us.plan_id) OR
                        (us.plan_id IS NULL AND p.id = u.plan_id)
                    )
                    WHERE u.id = %s
                """, (user_id,))
                
                plan_info = cursor.fetchone()
                if not plan_info:
                    # 폴백: 기본 free 플랜 값으로 응답 구성
                    plan_info = {
                        'user_id': user_id,
                        'email': current_user.get('email'),
                        'plan_id': None,
                        'plan_name': 'free',
                        'display_name': 'Free',
                        'monthly_request_limit': 30000,
                        'rate_limit_per_minute': 60,
                        'current_usage': 0,
                        'last_reset_at': None,
                    }
                
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
                
                # 7. 최근 6개월 월별 사용량 조회 (api_type별) - 당월 포함
                # 당월부터 역순으로 6개월 (예: 9월이면 9월, 8월, 7월, 6월, 5월, 4월)
                six_months_ago = today.replace(day=1) - timedelta(days=150)  # 대략 5개월 전
                cursor.execute("""
                    SELECT 
                        YEAR(date) as year,
                        MONTH(date) as month_num,
                        api_type,
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as successful_requests,
                        SUM(failed_requests) as failed_requests
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND date >= %s
                    GROUP BY YEAR(date), MONTH(date), api_type
                    ORDER BY year, month_num, api_type
                """, (user_id, six_months_ago))
                
                monthly_usage_by_type = cursor.fetchall()
                
                # 월별 데이터 포맷팅 (정순으로 6개월: 4월부터 9월까지)
                monthly_usage_data = []
                # 5개월 전부터 시작 (4월)
                start_date = today.replace(day=1) - timedelta(days=150)
                current_date = start_date.replace(day=1)
                
                for i in range(6):  # 정순으로 6개월
                    year = current_date.year
                    month_num = current_date.month
                    
                    # 해당 월의 데이터 찾기
                    month_data = [item for item in monthly_usage_by_type if item['year'] == year and item['month_num'] == month_num]
                    
                    # api_type별로 데이터 정리
                    month_stats = {
                        'month': f"{year}년 {month_num}월",
                        'month_short': f"{month_num}월",
                        'handwriting': 0,
                        'abstract': 0,
                        'imagecaptcha': 0,
                        'total': 0,
                        'pass': 0
                    }
                    
                    for data in month_data:
                        api_type = data['api_type']
                        requests = data['total_requests'] or 0
                        month_stats[api_type] = requests
                        month_stats['total'] += requests
                    
                    # pass = total - (handwriting + abstract + imagecaptcha)
                    try:
                        calculated_pass = max(0, (month_stats.get('total') or 0) - (
                            (month_stats.get('handwriting') or 0) +
                            (month_stats.get('abstract') or 0) +
                            (month_stats.get('imagecaptcha') or 0)
                        ))
                    except Exception:
                        calculated_pass = 0
                    month_stats['pass'] = calculated_pass
                    
                    monthly_usage_data.append(month_stats)
                    
                    # 다음 달로 이동
                    if month_num == 12:
                        current_date = current_date.replace(year=year + 1, month=1, day=1)
                    else:
                        current_date = current_date.replace(month=month_num + 1, day=1)
                
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
                        "level_stats": level_stats,
                        "monthly_usage": monthly_usage_data
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
                    # 주간 라벨을 "M월 N주차"로 생성하기 위해 주 시작일을 함께 조회
                    cursor.execute("""
                        SELECT 
                            YEARWEEK(date, 3) as yw,
                            MIN(date) as week_start,
                            MONTH(MIN(date)) AS month_num,
                            FLOOR((DAYOFMONTH(MIN(date)) - 1) / 7) + 1 AS week_in_month,
                            SUM(total_requests) as total_requests,
                            SUM(successful_requests) as successful_requests,
                            SUM(failed_requests) as failed_requests,
                            AVG(avg_response_time) as avg_response_time
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s
                        GROUP BY YEARWEEK(date, 3)
                        ORDER BY week_start
                    """, (user_id, start_date))
                else:  # monthly
                    # 최근 90일 데이터(최대 약 3개월)
                    start_date = datetime.now().date() - timedelta(days=90)
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
                
                rows = cursor.fetchall()
                # 주간의 경우 프론트에서 바로 사용할 수 있도록 "date" 라벨을 추가 변환
                if period == "weekly":
                    stats_data = []
                    for r in rows or []:
                        try:
                            label = f"{int(r['month_num'])}월 {int(r['week_in_month'])}주차"
                        except Exception:
                            label = f"W{r.get('yw', '')}"
                        stats_data.append({
                            "date": label,
                            "total_requests": int(r.get("total_requests", 0)),
                            "successful_requests": int(r.get("successful_requests", 0)),
                            "failed_requests": int(r.get("failed_requests", 0)),
                            "avg_response_time": float(r.get("avg_response_time", 0) or 0.0),
                        })
                else:
                    stats_data = rows
                
                return {
                    "success": True,
                    "data": stats_data
                }
                
    except Exception as e:
        print(f"대시보드 통계 데이터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="대시보드 통계 데이터 조회에 실패했습니다")


@router.get("/dashboard/key-stats")
def get_user_key_stats(
    request: Request,
    period: Literal["daily", "weekly", "monthly"] = Query("daily"),
    api_type: Literal["all", "handwriting", "abstract", "imagecaptcha"] = Query("all"),
    api_key: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=365),
    current_user = Depends(require_auth),
):
    """로그인 사용자의 API 키/타입별 사용량 (누락 구간 0 채움)
    - 총 요청: api_request_logs (api_type별)
    - 성공/실패: request_logs (verify 엔드포인트별)
    - 리렌더링: 총 - 성공 - 실패
    - api_key 미지정 시: 사용자의 모든 키 합계
    - api_type=all: 타입 합계, 그 외: 지정 타입만
    """
    try:
        results: List[dict] = []
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 기간 경계(KST)
                from datetime import datetime, timedelta, timezone, date as _date
                kst = timezone(timedelta(hours=9))
                today = datetime.now(kst).date()

                # API 키 필터 조건
                api_key_filter = ""
                api_key_params = []
                if api_key:
                    api_key_filter = "AND arl.api_key = %s"
                    api_key_params = [api_key]

                # API 타입 필터 조건 (전체일 때는 필터 없음)
                api_type_filter = ""
                api_type_params = []
                if api_type != "all":
                    api_type_filter = "AND arl.api_type = %s"
                    api_type_params = [api_type]

                # verify 엔드포인트 경로
                verify_paths = ['/api/imagecaptcha-verify', '/api/abstract-verify', '/api/handwriting-verify']

                if period == "daily":
                    # 최근 N일 데이터 (기본 7일, 최대 365일)
                    safe_days = max(1, min(int(days), 365))
                    start_date = today - timedelta(days=safe_days - 1)
                    days_list = [today - timedelta(days=i) for i in range(safe_days - 1, -1, -1)]

                    # 총 요청: api_request_logs에서 api_type별 집계
                    total_sql = f"""
                        SELECT 
                            DATE(arl.created_at) AS d,
                            arl.api_type,
                            COUNT(*) AS total
                        FROM api_request_logs arl
                        JOIN api_keys ak ON arl.api_key = ak.key_id
                        WHERE ak.user_id = %s 
                          AND DATE(arl.created_at) >= %s
                          {api_key_filter}
                          {api_type_filter}
                        GROUP BY DATE(arl.created_at), arl.api_type
                        ORDER BY d, arl.api_type
                    """
                    total_params = [current_user["id"], start_date] + api_key_params + api_type_params
                    cursor.execute(total_sql, total_params)
                    total_rows = cursor.fetchall() or []

                    # 성공/실패: request_logs에서 verify 엔드포인트별 집계
                    result_sql = f"""
                        SELECT 
                            DATE(rl.request_time) AS d,
                            CASE
                                WHEN rl.path = '/api/imagecaptcha-verify' THEN 'imagecaptcha'
                                WHEN rl.path = '/api/abstract-verify' THEN 'abstract'
                                WHEN rl.path = '/api/handwriting-verify' THEN 'handwriting'
                                ELSE 'unknown'
                            END AS api_type,
                            SUM(CASE WHEN rl.status_code = 200 THEN 1 ELSE 0 END) AS success,
                            SUM(CASE WHEN rl.status_code IN (400,500) THEN 1 ELSE 0 END) AS failed
                        FROM request_logs rl
                        WHERE rl.user_id = %s 
                          AND DATE(rl.request_time) >= %s
                          AND rl.path IN (%s, %s, %s)
                          {api_key_filter.replace('arl.api_key', 'rl.api_key')}
                        GROUP BY DATE(rl.request_time), 
                                 CASE
                                     WHEN rl.path = '/api/imagecaptcha-verify' THEN 'imagecaptcha'
                                     WHEN rl.path = '/api/abstract-verify' THEN 'abstract'
                                     WHEN rl.path = '/api/handwriting-verify' THEN 'handwriting'
                                     ELSE 'unknown'
                                 END
                        ORDER BY d, api_type
                    """
                    result_params = [current_user["id"], start_date] + verify_paths + api_key_params
                    cursor.execute(result_sql, result_params)
                    result_rows = cursor.fetchall() or []

                    # 데이터 병합
                    total_data = {}
                    for row in total_rows:
                        d = str(row['d'])
                        api_type = row['api_type']
                        if d not in total_data:
                            total_data[d] = {}
                        total_data[d][api_type] = int(row['total'] or 0)

                    result_data = {}
                    for row in result_rows:
                        d = str(row['d'])
                        api_type = row['api_type']
                        if d not in result_data:
                            result_data[d] = {}
                        result_data[d][api_type] = {
                            'success': int(row['success'] or 0),
                            'failed': int(row['failed'] or 0)
                        }

                    # 결과 생성 - 데이터가 있는 날짜만 표시
                    all_dates = set(total_data.keys()) | set(result_data.keys())
                    for d_str in sorted(all_dates):
                        day_totals = total_data.get(d_str, {})
                        day_results = result_data.get(d_str, {})

                        if api_type == "all":
                            # 전체 합계 - 모든 타입의 데이터 합계
                            total = sum(day_totals.values())
                            success = sum(r.get('success', 0) for r in day_results.values())
                            failed = sum(r.get('failed', 0) for r in day_results.values())
                        else:
                            # 특정 타입만
                            total = day_totals.get(api_type, 0)
                            result = day_results.get(api_type, {})
                            success = result.get('success', 0)
                            failed = result.get('failed', 0)

                        # 데이터가 있는 경우만 결과에 추가
                        if total > 0 or success > 0 or failed > 0:
                            rate = round((success / total) * 100, 1) if total else 0.0
                            results.append({
                                "totalRequests": total,
                                "successfulSolves": success,
                                "failedAttempts": failed,
                                "successRate": rate,
                                "averageResponseTime": 0,
                                "date": d_str,
                            })

                elif period == "weekly":
                    start_date = today - timedelta(days=28)
                    
                    # 총 요청: api_request_logs에서 주별 집계
                    total_sql = f"""
                        SELECT 
                            YEARWEEK(arl.created_at, 3) AS yw,
                            MIN(DATE(arl.created_at)) AS week_start,
                            arl.api_type,
                            COUNT(*) AS total
                        FROM api_request_logs arl
                        JOIN api_keys ak ON arl.api_key = ak.key_id
                        WHERE ak.user_id = %s 
                          AND DATE(arl.created_at) >= %s
                          {api_key_filter}
                          {api_type_filter}
                        GROUP BY YEARWEEK(arl.created_at, 3), arl.api_type
                        ORDER BY yw, arl.api_type
                    """
                    total_params = [current_user["id"], start_date] + api_key_params + api_type_params
                    cursor.execute(total_sql, total_params)
                    total_rows = cursor.fetchall() or []

                    # 성공/실패: request_logs에서 주별 집계
                    result_sql = f"""
                        SELECT 
                            YEARWEEK(rl.request_time, 3) AS yw,
                            MIN(DATE(rl.request_time)) AS week_start,
                            CASE
                                WHEN rl.path = '/api/imagecaptcha-verify' THEN 'imagecaptcha'
                                WHEN rl.path = '/api/abstract-verify' THEN 'abstract'
                                WHEN rl.path = '/api/handwriting-verify' THEN 'handwriting'
                                ELSE 'unknown'
                            END AS api_type,
                            SUM(CASE WHEN rl.status_code = 200 THEN 1 ELSE 0 END) AS success,
                            SUM(CASE WHEN rl.status_code IN (400,500) THEN 1 ELSE 0 END) AS failed
                        FROM request_logs rl
                        WHERE rl.user_id = %s 
                          AND DATE(rl.request_time) >= %s
                          AND rl.path IN (%s, %s, %s)
                          {api_key_filter.replace('arl.api_key', 'rl.api_key')}
                        GROUP BY YEARWEEK(rl.request_time, 3), 
                                 CASE
                                     WHEN rl.path = '/api/imagecaptcha-verify' THEN 'imagecaptcha'
                                     WHEN rl.path = '/api/abstract-verify' THEN 'abstract'
                                     WHEN rl.path = '/api/handwriting-verify' THEN 'handwriting'
                                     ELSE 'unknown'
                                 END
                        ORDER BY yw, api_type
                    """
                    result_params = [current_user["id"], start_date] + verify_paths + api_key_params
                    cursor.execute(result_sql, result_params)
                    result_rows = cursor.fetchall() or []

                    # 데이터 병합 및 결과 생성
                    total_data = {}
                    for row in total_rows:
                        yw = row['yw']
                        api_type = row['api_type']
                        if yw not in total_data:
                            total_data[yw] = {'week_start': row['week_start']}
                        total_data[yw][api_type] = int(row['total'] or 0)

                    result_data = {}
                    for row in result_rows:
                        yw = row['yw']
                        api_type = row['api_type']
                        if yw not in result_data:
                            result_data[yw] = {}
                        result_data[yw][api_type] = {
                            'success': int(row['success'] or 0),
                            'failed': int(row['failed'] or 0)
                        }

                    # 주간 결과 생성 - 데이터가 있는 주만 표시
                    all_weeks = set(total_data.keys()) | set(result_data.keys())
                    for yw in sorted(all_weeks):
                        if yw not in total_data:
                            continue
                            
                        data = total_data[yw]
                        week_start = data['week_start']
                        month = week_start.month
                        day = week_start.day
                        week_in_month = ((day - 1) // 7) + 1
                        label = f"{month}월 {week_in_month}주차"

                        day_totals = {k: v for k, v in data.items() if k != 'week_start'}
                        day_results = result_data.get(yw, {})

                        if api_type == "all":
                            total = sum(day_totals.values())
                            success = sum(r.get('success', 0) for r in day_results.values())
                            failed = sum(r.get('failed', 0) for r in day_results.values())
                        else:
                            total = day_totals.get(api_type, 0)
                            result = day_results.get(api_type, {})
                            success = result.get('success', 0)
                            failed = result.get('failed', 0)

                        # 데이터가 있는 경우만 결과에 추가
                        if total > 0 or success > 0 or failed > 0:
                            rate = round((success / total) * 100, 1) if total else 0.0
                            results.append({
                                "totalRequests": total,
                                "successfulSolves": success,
                                "failedAttempts": failed,
                                "successRate": rate,
                                "averageResponseTime": 0,
                                "date": label,
                            })

                else:  # monthly
                    start_date = today - timedelta(days=365)
                    
                    # 총 요청: api_request_logs에서 월별 집계
                    total_sql = f"""
                        SELECT 
                            DATE_FORMAT(arl.created_at, '%%Y-%%m') AS ym,
                            arl.api_type,
                            COUNT(*) AS total
                        FROM api_request_logs arl
                        JOIN api_keys ak ON arl.api_key = ak.key_id
                        WHERE ak.user_id = %s 
                          AND DATE(arl.created_at) >= %s
                          {api_key_filter}
                          {api_type_filter}
                        GROUP BY DATE_FORMAT(arl.created_at, '%%Y-%%m'), arl.api_type
                        ORDER BY ym, arl.api_type
                    """
                    total_params = [current_user["id"], start_date] + api_key_params + api_type_params
                    cursor.execute(total_sql, total_params)
                    total_rows = cursor.fetchall() or []

                    # 성공/실패: request_logs에서 월별 집계
                    result_sql = f"""
                        SELECT 
                            DATE_FORMAT(rl.request_time, '%%Y-%%m') AS ym,
                            CASE
                                WHEN rl.path = '/api/imagecaptcha-verify' THEN 'imagecaptcha'
                                WHEN rl.path = '/api/abstract-verify' THEN 'abstract'
                                WHEN rl.path = '/api/handwriting-verify' THEN 'handwriting'
                                ELSE 'unknown'
                            END AS api_type,
                            SUM(CASE WHEN rl.status_code = 200 THEN 1 ELSE 0 END) AS success,
                            SUM(CASE WHEN rl.status_code IN (400,500) THEN 1 ELSE 0 END) AS failed
                        FROM request_logs rl
                        WHERE rl.user_id = %s 
                          AND DATE(rl.request_time) >= %s
                          AND rl.path IN (%s, %s, %s)
                          {api_key_filter.replace('arl.api_key', 'rl.api_key')}
                        GROUP BY DATE_FORMAT(rl.request_time, '%%Y-%%m'), 
                                 CASE
                                     WHEN rl.path = '/api/imagecaptcha-verify' THEN 'imagecaptcha'
                                     WHEN rl.path = '/api/abstract-verify' THEN 'abstract'
                                     WHEN rl.path = '/api/handwriting-verify' THEN 'handwriting'
                                     ELSE 'unknown'
                                 END
                        ORDER BY ym, api_type
                    """
                    result_params = [current_user["id"], start_date] + verify_paths + api_key_params
                    cursor.execute(result_sql, result_params)
                    result_rows = cursor.fetchall() or []

                    # 데이터 병합 및 결과 생성
                    total_data = {}
                    for row in total_rows:
                        ym = row['ym']
                        api_type = row['api_type']
                        if ym not in total_data:
                            total_data[ym] = {}
                        total_data[ym][api_type] = int(row['total'] or 0)

                    result_data = {}
                    for row in result_rows:
                        ym = row['ym']
                        api_type = row['api_type']
                        if ym not in result_data:
                            result_data[ym] = {}
                        result_data[ym][api_type] = {
                            'success': int(row['success'] or 0),
                            'failed': int(row['failed'] or 0)
                        }

                    # 월간 결과 생성 - 데이터가 있는 월만 표시
                    all_months = set(total_data.keys()) | set(result_data.keys())
                    for ym in sorted(all_months):
                        if ym not in total_data:
                            continue
                            
                        day_totals = total_data[ym]
                        day_results = result_data.get(ym, {})

                        if api_type == "all":
                            total = sum(day_totals.values())
                            success = sum(r.get('success', 0) for r in day_results.values())
                            failed = sum(r.get('failed', 0) for r in day_results.values())
                        else:
                            total = day_totals.get(api_type, 0)
                            result = day_results.get(api_type, {})
                            success = result.get('success', 0)
                            failed = result.get('failed', 0)

                        # 데이터가 있는 경우만 결과에 추가
                        if total > 0 or success > 0 or failed > 0:
                            rate = round((success / total) * 100, 1) if total else 0.0
                            results.append({
                                "totalRequests": total,
                                "successfulSolves": success,
                                "failedAttempts": failed,
                                "successRate": rate,
                                "averageResponseTime": 0,
                                "date": ym,
                            })

                return {
                    "success": True,
                    "data": results
                }

    except Exception as e:
        print(f"key-stats 수집 실패: {e}")
        raise HTTPException(status_code=500, detail=f"key-stats 수집 실패: {e}")


@router.get("/dashboard/usage-limits")
def get_usage_limits(request: Request, current_user = Depends(require_auth)):
    """사용자별 API 사용량 제한 정보 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자 플랜 정보 조회 (users.plan_id → plans 테이블)
                cursor.execute(
                    """
                    SELECT p.plan_type, p.rate_limit_per_minute, p.monthly_request_limit, p.concurrent_requests,
                           p.display_name, p.features
                    FROM users u
                    LEFT JOIN plans p ON u.plan_id = p.id
                    WHERE u.id = %s
                    """,
                    (current_user["id"],)
                )
                plan_data = cursor.fetchone()
                
                # 기본 플랜 정보 (plan_type이 없으면 'free'로 설정)
                plan_type = plan_data.get("plan_type", "free") if plan_data else "free"
                
                # 플랜별 제한 설정 (plans 테이블에서 가져온 값 또는 기본값)
                if plan_data:
                    limits = {
                        "perMinute": plan_data.get("rate_limit_per_minute", 60),
                        "perDay": 1000,  # 일일 제한을 1000으로 고정
                        "perMonth": plan_data.get("monthly_request_limit", 30000)
                    }
                else:
                    # 기본 free 플랜 제한
                    limits = {"perMinute": 60, "perDay": 1000, "perMonth": 30000}
                
                # 현재 사용량 조회 (daily_user_api_stats 테이블에서)
                now = datetime.now()
                
                # 오늘 사용량 조회 (NULL 값 안전 처리)
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(total_requests), 0) as total_requests,
                        COALESCE(SUM(successful_requests), 0) as successful_requests,
                        COALESCE(SUM(failed_requests), 0) as failed_requests
                    FROM daily_user_api_stats 
                    WHERE user_id = %s AND date = CURDATE()
                    """,
                    (current_user["id"],)
                )
                
                today_usage = cursor.fetchone()
                
                # 이번 달 사용량 조회
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(total_requests), 0) as total_requests,
                        COALESCE(SUM(successful_requests), 0) as successful_requests,
                        COALESCE(SUM(failed_requests), 0) as failed_requests
                    FROM daily_user_api_stats 
                    WHERE user_id = %s AND date >= %s
                    """,
                    (current_user["id"], month_start)
                )
                
                month_usage = cursor.fetchone()
                
                # 분당 사용량 조회 (최근 1분간 요청 수)
                cursor.execute(
                    """
                    SELECT COUNT(*) as minute_requests
                    FROM api_request_logs arl
                    JOIN api_keys ak ON arl.api_key = ak.key_id
                    WHERE ak.user_id = %s 
                    AND arl.created_at >= DATE_SUB(NOW(), INTERVAL 1 MINUTE)
                    """,
                    (current_user["id"],)
                )
                minute_usage = cursor.fetchone()
                
                # 현재 사용량 (기본값 0, NULL 값 안전 처리)
                current_usage = {
                    "perMinute": int(minute_usage.get("minute_requests") or 0) if minute_usage else 0,
                    "perDay": int(today_usage.get("total_requests") or 0) if today_usage else 0,
                    "perMonth": int(month_usage.get("total_requests") or 0) if month_usage else 0
                }
                
                # 리셋 시간 계산
                next_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if next_month.month == 12:
                    next_month = next_month.replace(year=next_month.year + 1, month=1)
                else:
                    next_month = next_month.replace(month=next_month.month + 1)
                
                reset_times = {
                    "perMinute": now.replace(second=0, microsecond=0) + timedelta(minutes=1),
                    "perDay": now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                    "perMonth": next_month
                }
                
                # 상태 판단 (안전한 숫자 비교)
                status = "normal"
                per_minute_usage = int(current_usage.get("perMinute") or 0)
                per_day_usage = int(current_usage.get("perDay") or 0)
                per_month_usage = int(current_usage.get("perMonth") or 0)
                
                per_minute_limit = int(limits.get("perMinute") or 60)
                per_day_limit = int(limits.get("perDay") or 1000)
                per_month_limit = int(limits.get("perMonth") or 30000)
                
                if per_minute_usage >= per_minute_limit * 0.9:
                    status = "warning"
                if per_day_usage >= per_day_limit * 0.9:
                    status = "warning"
                if per_month_usage >= per_month_limit * 0.9:
                    status = "critical"
                if (per_minute_usage >= per_minute_limit or 
                    per_day_usage >= per_day_limit or 
                    per_month_usage >= per_month_limit):
                    status = "exceeded"
                
                return {
                    "success": True,
                    "data": {
                        "plan": plan_type,
                        "planDisplayName": plan_data.get("display_name", "Free") if plan_data else "Free",
                        "limits": limits,
                        "currentUsage": current_usage,
                        "resetTimes": reset_times,
                        "status": status
                    }
                }
                
    except Exception as e:
        print(f"사용량 제한 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="사용량 제한 조회에 실패했습니다")


@router.get("/dashboard/api-key-usage/{api_key}")
def get_api_key_usage(api_key: str, request: Request, current_user = Depends(require_auth)):
    """특정 API 키의 사용량 통계 조회"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # API 키 소유권 확인
                cursor.execute(
                    """
                    SELECT ak.key_id, ak.name, ak.user_id
                    FROM api_keys ak
                    WHERE ak.key_id = %s AND ak.user_id = %s
                    """,
                    (api_key, current_user["id"])
                )
                key_info = cursor.fetchone()
                
                if not key_info:
                    raise HTTPException(status_code=404, detail="API 키를 찾을 수 없거나 접근 권한이 없습니다")
                
                # API 키 사용량 통계 조회 (최근 30일)
                start_date = datetime.now().date() - timedelta(days=30)
                cursor.execute(
                    """
                    SELECT 
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as successful_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time,
                        MAX(date) as last_used
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND api_key = %s AND date >= %s
                    """,
                    (current_user["id"], api_key, start_date)
                )
                
                stats = cursor.fetchone()
                
                return {
                    "success": True,
                    "data": {
                        "apiKey": api_key,
                        "name": key_info.get("name", ""),
                        "totalRequests": stats.get("total_requests", 0) or 0,
                        "successRequests": stats.get("successful_requests", 0) or 0,
                        "failedRequests": stats.get("failed_requests", 0) or 0,
                        "avgResponseTime": round(stats.get("avg_response_time", 0) or 0, 2),
                        "lastUsed": stats.get("last_used")
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"API 키 사용량 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="API 키 사용량 조회에 실패했습니다")


@router.post("/dashboard/cleanup-duplicates")
def cleanup_duplicates(request: Request, current_user = Depends(require_auth)):
    """중복 데이터 정리 (관리자만 가능)"""
    try:
        # 관리자 권한 확인
        if not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
        # 중복 데이터 정리 실행
        deleted_count = cleanup_duplicate_request_statistics()
        
        return {
            "success": True,
            "data": {
                "deletedCount": deleted_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"중복 데이터 정리 실패: {e}")
        raise HTTPException(status_code=500, detail="중복 데이터 정리에 실패했습니다")

@router.get("/dashboard/error-analysis")
def get_error_analysis(
    request: Request,
    period: str = Query("7days", description="분석 기간: 1day, 7days, 30days"),
    api_key: Optional[str] = Query(None, description="특정 API 키 필터"),
    current_user = Depends(require_auth)
):
    """오류 유형 분석 데이터 조회"""
    try:
        user_id = current_user["id"]
        
        # 기간별 날짜 필터 생성
        if period == "1day":
            date_filter = "DATE(arl.created_at) = CURDATE()"
        elif period == "7days":
            date_filter = "arl.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        elif period == "30days":
            date_filter = "arl.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
        else:
            date_filter = "arl.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"  # 기본값
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # API 키 필터 조건
                api_key_filter = ""
                params = [user_id]
                if api_key:
                    api_key_filter = "AND ak.key_id = %s"
                    params.append(api_key)
                
                # 오류 유형별 집계 쿼리
                error_query = f"""
                    SELECT 
                        CASE 
                            WHEN arl.status_code >= 400 AND arl.status_code < 500 THEN '4xx_client_error'
                            WHEN arl.status_code >= 500 AND arl.status_code < 600 THEN '5xx_server_error'
                            WHEN arl.response_time > 5000 THEN 'timeout'
                            WHEN arl.status_code < 200 OR arl.status_code >= 300 THEN 'other_error'
                            ELSE 'success'
                        END as error_type,
                        COUNT(*) as error_count
                    FROM api_request_logs arl
                    JOIN api_keys ak ON arl.api_key = ak.key_id
                    WHERE ak.user_id = %s 
                    AND {date_filter}
                    {api_key_filter}
                    GROUP BY error_type
                    ORDER BY error_count DESC
                """
                
                cursor.execute(error_query, params)
                error_results = cursor.fetchall()
                
                # 전체 요청 수 계산
                total_requests = sum(row['error_count'] for row in error_results)
                
                # 오류 유형 매핑
                error_type_names = {
                    '4xx_client_error': '클라이언트 오류 (4xx)',
                    '5xx_server_error': '서버 오류 (5xx)', 
                    'timeout': '타임아웃 (>5초)',
                    'other_error': '기타 오류',
                    'success': '성공'
                }
                
                # 모든 오류 유형을 기본값 0으로 초기화
                all_error_types = ['4xx_client_error', '5xx_server_error', 'timeout', 'other_error']
                error_data = {error_type: 0 for error_type in all_error_types}
                
                # 실제 데이터로 업데이트
                for row in error_results:
                    error_type = row['error_type']
                    if error_type in error_data:  # 성공 요청은 제외
                        error_data[error_type] = int(row['error_count'])
                
                # 전체 오류 수 계산 (성공 제외)
                total_errors = sum(error_data.values())
                
                # 결과 가공 - 항상 4가지 유형 모두 표시
                error_analysis = []
                for error_type in all_error_types:
                    count = error_data[error_type]
                    percentage = (count / total_errors * 100) if total_errors > 0 else 0
                    
                    error_analysis.append({
                        "type": error_type_names.get(error_type, error_type),
                        "count": count,
                        "percentage": round(percentage, 1)
                    })
                
                return {
                    "success": True,
                    "data": {
                        "error_types": error_analysis,
                        "total_requests": total_requests,
                        "period": period,
                        "api_key": api_key
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"오류 분석 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"오류 분석 조회에 실패했습니다: {str(e)}")
