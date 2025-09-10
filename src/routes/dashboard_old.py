from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import Literal, Optional, List
from datetime import date, timedelta, datetime
from src.config.database import get_db_connection, cleanup_duplicate_request_statistics
from src.routes.auth import get_current_user_from_request
from src.middleware.usage_tracking import ApiUsageTracker
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
                    LEFT JOIN user_subscriptions us ON u.id = us.user_id
                    LEFT JOIN plans p ON us.plan_id = p.id
                    WHERE u.id = %s AND us.status = 'active'
                """, (user_id,))
                
                plan_info = cursor.fetchone()
                if not plan_info:
                    raise HTTPException(status_code=404, detail="사용자 플랜 정보를 찾을 수 없습니다")
                
                # 2. 오늘의 API 사용량 조회 (캡차 타입별)
                today = datetime.now().date()
                cursor.execute("""
                    SELECT 
                        api_type,
                        SUM(total_requests) as total_requests,
                        SUM(successful_requests) as successful_requests,
                        SUM(failed_requests) as failed_requests,
                        AVG(avg_response_time) as avg_response_time
                    FROM daily_user_api_stats
                    WHERE user_id = %s AND date = %s
                    GROUP BY api_type
                """, (user_id, today))
                
                today_stats = cursor.fetchall()
                
                # 3. 이번 달 총 사용량 조회
                month_start = today.replace(day=1)
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
                for stat in today_stats:
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
                        "today_stats": {
                            "total_requests": total_requests,
                            "successful_requests": sum(stat['successful_requests'] or 0 for stat in today_stats),
                            "failed_requests": sum(stat['failed_requests'] or 0 for stat in today_stats),
                            "success_rate": round((sum(stat['successful_requests'] or 0 for stat in today_stats) / total_requests * 100), 1) if total_requests > 0 else 0,
                            "avg_response_time": round(sum(stat['avg_response_time'] or 0 for stat in today_stats) / len(today_stats), 2) if today_stats else 0
                        },
                        "captcha_stats": captcha_stats,
                        "level_stats": level_stats
                    }
                }
                
    except Exception as e:
        print(f"대시보드 분석 데이터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="대시보드 데이터 조회에 실패했습니다")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 최근 7일
                cursor.execute(
                    """
                    SELECT date, total_requests, success_count, failure_count
                    FROM request_statistics
                    WHERE date >= CURDATE() - INTERVAL 6 DAY
                    ORDER BY date ASC
                    """
                )
                rows = cursor.fetchall() or []
                for r in rows:
                    total = int(r.get("total_requests", 0))
                    success = int(r.get("success_count", 0))
                    failed = int(r.get("failure_count", 0))
                    rate = round((success / total) * 100, 1) if total else 0.0
                    daily.append(
                        {
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,  # 추후 실제 값 연동
                        }
                    )

                # 최근 4주 (주간)
                cursor.execute(
                    """
                    SELECT YEARWEEK(date, 3) AS yw, SUM(total_requests) AS total, SUM(success_count) AS success, SUM(failure_count) AS failed
                    FROM request_statistics
                    WHERE date >= CURDATE() - INTERVAL 28 DAY
                    GROUP BY yw
                    ORDER BY yw ASC
                    """
                )
                rows = cursor.fetchall() or []
                for r in rows:
                    total = int(r.get("total", 0))
                    success = int(r.get("success", 0))
                    failed = int(r.get("failed", 0))
                    rate = round((success / total) * 100, 1) if total else 0.0
                    weekly.append(
                        {
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                        }
                    )

                # 최근 3개월 (월간)
                cursor.execute(
                    """
                    SELECT DATE_FORMAT(date, '%Y-%m') AS ym, SUM(total_requests) AS total, SUM(success_count) AS success, SUM(failure_count) AS failed
                    FROM request_statistics
                    WHERE date >= (CURDATE() - INTERVAL 2 MONTH) - INTERVAL DAYOFMONTH(CURDATE())-1 DAY
                    GROUP BY ym
                    ORDER BY ym ASC
                    """
                )
                rows = cursor.fetchall() or []
                for r in rows:
                    total = int(r.get("total", 0))
                    success = int(r.get("success", 0))
                    failed = int(r.get("failed", 0))
                    rate = round((success / total) * 100, 1) if total else 0.0
                    monthly.append(
                        {
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                        }
                    )

        return {"success": True, "data": {"dailyStats": daily, "weeklyStats": weekly, "monthlyStats": monthly, "realtimeMetrics": realtime}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analytics 수집 실패: {e}")


def ensure_daily_stats_data():
    """daily_api_stats 테이블에 누락된 날짜 데이터를 0으로 채워넣기"""
    try:
        from datetime import date, timedelta, timezone, datetime
        
        # Python에서 KST 기준 오늘 날짜 계산
        kst_tz = timezone(timedelta(hours=9))
        kst_today = datetime.now(kst_tz).date()
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 최근 7일간의 모든 날짜에 대해 데이터가 있는지 확인
                cursor.execute("""
                    SELECT DISTINCT date FROM daily_api_stats 
                    WHERE date >= %s
                    ORDER BY date
                """, (kst_today - timedelta(days=6),))
                existing_dates = [row['date'] for row in cursor.fetchall()]
                
                # 누락된 날짜 찾기 (KST 기준)
                all_dates = []
                for i in range(7):
                    check_date = kst_today - timedelta(days=i)
                    all_dates.append(check_date)
                
                missing_dates = [d for d in all_dates if d not in existing_dates]
                
                # 누락된 날짜에 대해 0 데이터 삽입
                for missing_date in missing_dates:
                    for api_type in ['handwriting', 'abstract', 'imagecaptcha']:
                        cursor.execute("""
                            INSERT IGNORE INTO daily_api_stats 
                            (date, api_type, total_requests, success_requests, failed_requests, avg_response_time)
                            VALUES (%s, %s, 0, 0, 0, 0.00)
                        """, (missing_date, api_type))
                
                conn.commit()
                return len(missing_dates)
    except Exception as e:
        print(f"⚠️ daily_api_stats 데이터 보완 실패: {e}")
        return 0


@router.get("/dashboard/stats")
def get_dashboard_stats(
    request: Request, 
    period: Literal["daily", "weekly", "monthly"] = Query("daily"),
    api_type: Literal["all", "handwriting", "abstract", "imagecaptcha"] = Query("all"),
    current_user = Depends(require_auth)
):
    """기간별 캡차 통계 (API별 분리)
    - period: daily(7일), weekly(4주), monthly(3개월)
    - api_type: all(전체), handwriting(필기), abstract(추상), imagecaptcha(이미지)
    응답 항목은 프런트의 CaptchaStats 포맷을 따름.
    """
    try:
        # daily_api_stats 테이블에 누락된 데이터 보완
        if period == "daily":
            ensure_daily_stats_data()
        
        results = []
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if period == "daily":
                    # Python에서 KST 기준 날짜 계산
                    from datetime import date, timedelta, timezone, datetime
                    kst_tz = timezone(timedelta(hours=9))
                    kst_today = datetime.now(kst_tz).date()
                    start_date = kst_today - timedelta(days=6)
                    
                    # daily_api_stats 테이블을 메인 데이터 소스로 사용
                    if api_type == "all":
                        cursor.execute(
                            """
                            SELECT date, 
                                   SUM(total_requests) as total,
                                   SUM(success_requests) as success,
                                   SUM(failed_requests) as failed
                            FROM daily_api_stats
                            WHERE date >= %s
                            GROUP BY date
                            ORDER BY date ASC
                            """,
                            (start_date,)
                        )
                    else:
                        # API 타입별 필터링
                        api_type_mapping = {
                            "handwriting": "handwriting",
                            "abstract": "abstract", 
                            "imagecaptcha": "imagecaptcha"
                        }
                        target_api_type = api_type_mapping.get(api_type, "handwriting")
                        cursor.execute(
                            """
                            SELECT date, 
                                   total_requests as total,
                                   success_requests as success,
                                   failed_requests as failed
                            FROM daily_api_stats
                            WHERE date >= %s
                            AND api_type = %s
                            ORDER BY date ASC
                            """,
                            (start_date, target_api_type)
                        )
                    rows = cursor.fetchall() or []
                    for r in rows:
                        total = int(r.get("total", 0))
                        success = int(r.get("success", 0))
                        failed = int(r.get("failed", 0))
                        rate = round((success / total) * 100, 1) if total else 0.0
                        results.append({
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                            "date": r.get("date").strftime("%Y-%m-%d") if r.get("date") else None,
                        })
                elif period == "weekly":
                    # Python에서 KST 기준 날짜 계산
                    from datetime import date, timedelta, timezone, datetime
                    kst_tz = timezone(timedelta(hours=9))
                    kst_today = datetime.now(kst_tz).date()
                    start_date = kst_today - timedelta(days=28)
                    
                    # daily_api_stats 테이블을 사용하여 주간 통계 계산
                    if api_type == "all":
                        cursor.execute(
                            """
                            SELECT YEARWEEK(date, 3) AS yw,
                                   SUM(total_requests) AS total,
                                   SUM(success_requests) AS success,
                                   SUM(failed_requests) AS failed
                            FROM daily_api_stats
                            WHERE date >= %s
                            GROUP BY YEARWEEK(date, 3)
                            ORDER BY yw ASC
                            """,
                            (start_date,)
                        )
                    else:
                        api_type_mapping = {
                            "handwriting": "handwriting",
                            "abstract": "abstract", 
                            "imagecaptcha": "imagecaptcha"
                        }
                        target_api_type = api_type_mapping.get(api_type, "handwriting")
                        cursor.execute(
                            """
                            SELECT YEARWEEK(date, 3) AS yw,
                                   SUM(total_requests) AS total,
                                   SUM(success_requests) AS success,
                                   SUM(failed_requests) AS failed
                            FROM daily_api_stats
                            WHERE date >= %s
                            AND api_type = %s
                            GROUP BY YEARWEEK(date, 3)
                            ORDER BY yw ASC
                            """,
                            (start_date, target_api_type)
                        )
                    rows = cursor.fetchall() or []
                    for r in rows:
                        total = int(r.get("total", 0))
                        success = int(r.get("success", 0))
                        failed = int(r.get("failed", 0))
                        rate = round((success / total) * 100, 1) if total else 0.0
                        # 주간 라벨 생성 (예: 9월 1주)
                        yw = r.get("yw", "")
                        if yw:
                            # yw 형식: 202536 -> 2025년 36주차 (ISO 주차)
                            year = int(str(yw)[:4])
                            week_num = int(str(yw)[-2:])
                            from datetime import date, timedelta
                            # ISO 주차의 월요일 날짜 계산
                            week_start = date.fromisocalendar(year, week_num, 1)
                            month = week_start.month
                            # 월 기준 몇 번째 주인지 계산 (해당 월의 첫 날부터 카운트)
                            first_day_of_month = date(year, month, 1)
                            # first_day_of_month가 속한 주의 월요일
                            first_week_monday = first_day_of_month - timedelta(days=(first_day_of_month.isoweekday() - 1))
                            week_in_month = ((week_start - first_week_monday).days // 7) + 1
                            week_label = f"{month}월 {week_in_month}주"
                        else:
                            week_label = "Unknown"
                        results.append({
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                            "date": week_label,
                        })
                else:  # monthly
                    # Python에서 KST 기준 날짜 계산
                    from datetime import date, timedelta, timezone, datetime
                    kst_tz = timezone(timedelta(hours=9))
                    kst_today = datetime.now(kst_tz).date()
                    # 3개월 전 1일부터
                    start_date = kst_today.replace(day=1) - timedelta(days=60)
                    
                    # daily_api_stats 테이블을 사용하여 월간 통계 계산
                    if api_type == "all":
                        cursor.execute(
                            """
                            SELECT DATE_FORMAT(date, '%%Y-%%m') AS ym,
                                   SUM(total_requests) AS total,
                                   SUM(success_requests) AS success,
                                   SUM(failed_requests) AS failed
                            FROM daily_api_stats
                            WHERE date >= %s
                            GROUP BY DATE_FORMAT(date, '%%Y-%%m')
                            ORDER BY ym ASC
                            """,
                            (start_date,)
                        )
                    else:
                        api_type_mapping = {
                            "handwriting": "handwriting",
                            "abstract": "abstract", 
                            "imagecaptcha": "imagecaptcha"
                        }
                        target_api_type = api_type_mapping.get(api_type, "handwriting")
                        cursor.execute(
                            """
                            SELECT DATE_FORMAT(date, '%%Y-%%m') AS ym,
                                   SUM(total_requests) AS total,
                                   SUM(success_requests) AS success,
                                   SUM(failed_requests) AS failed
                            FROM daily_api_stats
                            WHERE date >= %s
                            AND api_type = %s
                            GROUP BY DATE_FORMAT(date, '%%Y-%%m')
                            ORDER BY ym ASC
                            """,
                            (start_date, target_api_type)
                        )
                    rows = cursor.fetchall() or []
                    for r in rows:
                        total = int(r.get("total", 0))
                        success = int(r.get("success", 0))
                        failed = int(r.get("failed", 0))
                        rate = round((success / total) * 100, 1) if total else 0.0
                        # 월간 라벨 생성 (예: 2025-08)
                        ym = r.get("ym", "")
                        month_label = ym.replace("-", "/") if ym else "Unknown"
                        results.append({
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                            "date": month_label,
                        })

        return {"success": True, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stats 수집 실패: {e}")


@router.get("/dashboard/key-stats")
def get_user_key_stats(
    request: Request,
    period: Literal["daily", "weekly", "monthly"] = Query("daily"),
    api_type: Literal["all", "handwriting", "abstract", "imagecaptcha"] = Query("all"),
    api_key: Optional[str] = Query(None),
    current_user = Depends(require_auth),
):
    """로그인 사용자의 API 키/타입별 사용량 (누락 구간 0 채움)
    - 데이터 소스: daily_user_api_stats
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

                def to_rows(rows, label_builder):
                    out = []
                    for r in rows:
                        total = int(r.get("total", 0))
                        success = int(r.get("success", 0))
                        failed = int(r.get("failed", 0))
                        rate = round((success / total) * 100, 1) if total else 0.0
                        out.append({
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                            "date": label_builder(r),
                        })
                    return out

                # 조건 구성
                params: list = [current_user["id"]]
                type_clause = ""
                if api_type != "all":
                    type_clause = " AND api_type = %s"
                    params.append(api_type)
                key_clause = ""
                if api_key:
                    key_clause = " AND api_key = %s"
                    params.append(api_key)

                if period == "daily":
                    start_date = today - timedelta(days=6)
                    # 0 채움용 라벨 테이블 생성
                    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
                    # 파라미터 순서: user_id, start_date, (api_type?), (api_key?)
                    base_sql = f"""
                        SELECT date, 
                               SUM(total_requests) AS total,
                               SUM(successful_requests) AS success,
                               SUM(failed_requests) AS failed
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s{type_clause}{key_clause}
                        GROUP BY date
                        ORDER BY date ASC
                        """
                    # 올바른 파라미터 바인딩
                    bind_params = [current_user["id"], start_date]
                    if api_type != "all":
                        bind_params.append(api_type)
                    if api_key:
                        bind_params.append(api_key)
                    cursor.execute(base_sql, bind_params)
                    rows = {r["date"]: r for r in (cursor.fetchall() or [])}
                    for d in days:
                        r = rows.get(d)
                        if r:
                            total = int(r.get("total", 0))
                            success = int(r.get("success", 0))
                            failed = int(r.get("failed", 0))
                        else:
                            total = success = failed = 0
                        rate = round((success / total) * 100, 1) if total else 0.0
                        results.append({
                            "totalRequests": total,
                            "successfulSolves": success,
                            "failedAttempts": failed,
                            "successRate": rate,
                            "averageResponseTime": 0,
                            "date": d.strftime("%Y-%m-%d"),
                        })

                elif period == "weekly":
                    start_date = today - timedelta(days=28)
                    base_sql = f"""
                        SELECT YEARWEEK(date, 3) AS yw,
                               SUM(total_requests) AS total,
                               SUM(successful_requests) AS success,
                               SUM(failed_requests) AS failed
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s{type_clause}{key_clause}
                        GROUP BY YEARWEEK(date, 3)
                        ORDER BY yw ASC
                        """
                    bind_params = [current_user["id"], start_date]
                    if api_type != "all":
                        bind_params.append(api_type)
                    if api_key:
                        bind_params.append(api_key)
                    cursor.execute(base_sql, bind_params)
                    agg = cursor.fetchall() or []
                    # 4주 라벨 생성 후 매칭
                    from datetime import date as _dt
                    labels = []
                    for i in range(4, 0, -1):
                        wk_start = today - timedelta(days=i * 7)
                        labels.append(wk_start.isocalendar())  # (year, week, weekday)
                    # 매핑
                    def week_label(yw):
                        year = int(str(yw)[:4]); week_num = int(str(yw)[-2:])
                        ws = _date.fromisocalendar(year, week_num, 1)
                        month = ws.month
                        first_day = _date(year, month, 1)
                        first_week_monday = first_day - timedelta(days=(first_day.isoweekday() - 1))
                        w_in_m = ((ws - first_week_monday).days // 7) + 1
                        return f"{month}월 {w_in_m}주"
                    results = to_rows(agg, lambda r: week_label(r.get("yw")))

                else:  # monthly
                    # 최근 3개월(해당 월 1일부터)
                    start_date = today.replace(day=1) - timedelta(days=60)
                    base_sql = f"""
                        SELECT DATE_FORMAT(date, '%%Y-%%m') AS ym,
                               SUM(total_requests) AS total,
                               SUM(successful_requests) AS success,
                               SUM(failed_requests) AS failed
                        FROM daily_user_api_stats
                        WHERE user_id = %s AND date >= %s{type_clause}{key_clause}
                        GROUP BY DATE_FORMAT(date, '%%Y-%%m')
                        ORDER BY ym ASC
                        """
                    bind_params = [current_user["id"], start_date]
                    if api_type != "all":
                        bind_params.append(api_type)
                    if api_key:
                        bind_params.append(api_key)
                    cursor.execute(base_sql, bind_params)
                    agg = cursor.fetchall() or []
                    results = to_rows(agg, lambda r: (r.get("ym") or "").replace("-", "/"))

        return {"success": True, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"key-stats 수집 실패: {e}")


@router.get("/dashboard/realtime")
def get_realtime_metrics(request: Request, current_user = Depends(require_auth)):
    try:
        return {
            "success": True,
            "data": {
                "currentActiveUsers": 128,
                "requestsPerMinute": 124,
                "systemHealth": "healthy",
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"realtime 수집 실패: {e}")


@router.get("/captcha/performance")
def get_captcha_performance(request: Request, current_user = Depends(require_auth)):
    """엔드포인트별 일일 사용량 집계 (endpoint_usage_daily 참조). 데이터 없으면 기본값"""
    try:
        items = []
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT endpoint, SUM(requests) AS requests, ROUND(AVG(avg_ms)) AS avg_ms
                    FROM endpoint_usage_daily
                    WHERE date >= CURDATE() - INTERVAL 7 DAY
                    GROUP BY endpoint
                    ORDER BY requests DESC
                    LIMIT 50
                    """
                )
                rows = cursor.fetchall() or []
                for r in rows:
                    items.append(
                        {
                            "endpoint": r.get("endpoint"),
                            "requests": _safe_int(r.get("requests"), 0),
                            "avg_ms": _safe_int(r.get("avg_ms"), 0),
                        }
                    )

        # 데이터가 없으면 기본 셋 제공
        if not items:
            items = [
                {"endpoint": "/api/captcha/verify", "requests": 0, "avg_ms": 0},
                {"endpoint": "/api/captcha/init", "requests": 0, "avg_ms": 0},
            ]

        return {"success": True, "data": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"performance 조회 실패: {e}")


@router.get("/captcha/logs")
def get_captcha_logs(
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    status: Optional[Literal["success", "failed"]] = None,
    current_user = Depends(require_auth)
):
    """캡차 로그는 아직 원천 테이블이 없으므로 빈 목록/페이지 정보 반환"""
    return {
        "success": True,
        "data": [],
        "message": "로그 원천 테이블 미구현 상태. 추후 request_logs 연동 예정.",
        "page": page,
        "pageSize": pageSize,
        "total": 0,
    }


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
                        "perDay": plan_data.get("monthly_request_limit", 1000) / 30,  # 월간 제한을 일일로 나눔
                        "perMonth": plan_data.get("monthly_request_limit", 30000)
                    }
                else:
                    # 기본 free 플랜 제한
                    limits = {"perMinute": 60, "perDay": 1000, "perMonth": 30000}
                
                # 현재 사용량 조회 (user_usage_tracking 테이블에서 캡차 사용량만)
                now = datetime.now()
                
                # user_usage_tracking 테이블에서 오늘 사용량 조회
                cursor.execute(
                    """
                    SELECT 
                        per_minute_count,
                        per_day_count,
                        per_month_count
                    FROM user_usage_tracking 
                    WHERE user_id = %s AND tracking_date = CURDATE()
                    """,
                    (current_user["id"],)
                )
                
                usage_data = cursor.fetchone()
                if usage_data:
                    per_minute_usage = usage_data.get("per_minute_count", 0)
                    per_day_usage = usage_data.get("per_day_count", 0)
                    per_month_usage = usage_data.get("per_month_count", 0)
                else:
                    # 오늘 사용량 기록이 없으면 0
                    per_minute_usage = 0
                    per_day_usage = 0
                    per_month_usage = 0
                
                # user_subscriptions 테이블에서 현재 구독 정보 확인
                cursor.execute(
                    """
                    SELECT us.current_usage, us.last_reset_at, p.plan_type, p.display_name
                    FROM user_subscriptions us
                    JOIN plans p ON us.plan_id = p.id
                    WHERE us.user_id = %s 
                    AND us.status = 'active'
                    AND (us.start_date IS NULL OR us.start_date <= CURDATE())
                    AND (us.end_date IS NULL OR us.end_date >= CURDATE())
                    ORDER BY us.created_at DESC
                    LIMIT 1
                    """,
                    (current_user["id"],)
                )
                subscription_data = cursor.fetchone()
                
                # 구독 정보가 있으면 해당 정보 사용
                if subscription_data:
                    plan_type = subscription_data.get("plan_type", plan_type)
                    plan_display_name = subscription_data.get("display_name", plan_data.get("display_name", plan_type.upper()))
                    # 구독의 current_usage는 월간 사용량으로 사용 가능
                    if subscription_data.get("current_usage"):
                        per_month_usage = subscription_data.get("current_usage")
                else:
                    plan_display_name = plan_data.get("display_name", plan_type.upper()) if plan_data else plan_type.upper()
                
                # request_logs 테이블에서 실제 사용량 계산 (누락된 부분)
                cursor.execute("""
                    SELECT COUNT(*) as monthly_requests
                    FROM request_logs 
                    WHERE user_id = %s 
                    AND request_time >= DATE_FORMAT(NOW(), '%%Y-%%m-01')  -- 이번 달 1일부터
                    AND request_time < DATE_FORMAT(NOW() + INTERVAL 1 MONTH, '%%Y-%%m-01')  -- 다음 달 1일 전까지
                """, (current_user["id"],))
                
                monthly_requests_result = cursor.fetchone()
                if monthly_requests_result:
                    # request_logs에서 계산된 실제 사용량이 있으면 사용
                    actual_monthly_usage = monthly_requests_result.get("monthly_requests", 0)
                    if actual_monthly_usage > 0:
                        per_month_usage = actual_monthly_usage
                
                # 리셋 시간 계산
                next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1)).isoformat()
                next_day = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
                next_month = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1).isoformat()
                
                # 상태 결정
                def get_status(current, limit):
                    if current >= limit:
                        return "exceeded"
                    elif current >= limit * 0.9:
                        return "critical"
                    elif current >= limit * 0.7:
                        return "warning"
                    else:
                        return "normal"
                
                status = "normal"
                if (per_minute_usage >= limits["perMinute"] or 
                    per_day_usage >= limits["perDay"] or 
                    per_month_usage >= limits["perMonth"]):
                    status = "exceeded"
                elif (per_minute_usage >= limits["perMinute"] * 0.9 or 
                      per_day_usage >= limits["perDay"] * 0.9 or 
                      per_month_usage >= limits["perMonth"] * 0.9):
                    status = "critical"
                elif (per_minute_usage >= limits["perMinute"] * 0.7 or 
                      per_day_usage >= limits["perDay"] * 0.7 or 
                      per_month_usage >= limits["perMonth"] * 0.7):
                    status = "warning"
                
                return {
                    "success": True,
                    "data": {
                        "plan": plan_type,
                        "planDisplayName": plan_display_name,
                        "limits": limits,
                        "currentUsage": {
                            "perMinute": per_minute_usage,
                            "perDay": per_day_usage,
                            "perMonth": per_month_usage
                        },
                        "resetTimes": {
                            "perMinute": next_minute,
                            "perDay": next_day,
                            "perMonth": next_month
                        },
                        "status": status
                    }
                }
                
    except Exception as e:
        # 에러 발생 시 기본값 반환
        now = datetime.now()
        next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1)).isoformat()
        next_day = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
        next_month = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1).isoformat()
        
        return {
            "success": True,
            "data": {
                "plan": "free",
                "planDisplayName": "FREE",
                "limits": {"perMinute": 60, "perDay": 1000, "perMonth": 30000},
                "currentUsage": {"perMinute": 0, "perDay": 0, "perMonth": 0},
                "resetTimes": {
                    "perMinute": next_minute,
                    "perDay": next_day,
                    "perMonth": next_month
                },
                "status": "normal"
            }
        }

@router.get("/dashboard/api-key-usage/{api_key}")
def get_api_key_usage_stats(
    api_key: str,
    request: Request,
    current_user = Depends(require_auth)
):
    """특정 API 키의 사용량 통계 조회"""
    try:
        # API 키 소유자 확인
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id FROM api_keys WHERE key_id = %s
                """, (api_key,))
                
                api_key_owner = cursor.fetchone()
                if not api_key_owner:
                    raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다.")
                
                # 본인의 API 키만 조회 가능
                if api_key_owner['user_id'] != current_user['id']:
                    raise HTTPException(status_code=403, detail="본인의 API 키만 조회할 수 있습니다.")
        
        # API 키 사용량 통계 조회
        usage_stats = ApiUsageTracker.get_api_key_usage_stats(api_key)
        
        if not usage_stats:
            raise HTTPException(status_code=500, detail="사용량 통계를 조회할 수 없습니다.")
        
        return {
            "success": True,
            "data": {
                "apiKey": usage_stats['key_id'],
                "name": usage_stats['name'],
                "totalRequests": usage_stats['total_requests'],
                "successRequests": usage_stats['success_requests'],
                "failedRequests": usage_stats['failed_requests'],
                "avgResponseTime": usage_stats['avg_response_time'],
                "lastUsed": usage_stats['last_used_at'].isoformat() if usage_stats['last_used_at'] else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 키 사용량 조회 실패: {e}")


@router.post("/dashboard/cleanup-duplicates")
def cleanup_duplicate_statistics(request: Request, current_user = Depends(require_auth)):
    """request_statistics 테이블의 중복 데이터를 수동으로 정리"""
    try:
        deleted_count = cleanup_duplicate_request_statistics()
        
        return {
            "success": True,
            "message": f"중복 데이터 정리 완료: {deleted_count}건 삭제",
            "deletedCount": deleted_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"중복 데이터 정리 실패: {e}")