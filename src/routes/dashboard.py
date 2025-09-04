from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import Literal, Optional, List
from datetime import date, timedelta, datetime
from src.config.database import get_db_connection, cleanup_duplicate_request_statistics
from src.routes.auth import get_current_user_from_request
from src.middleware.usage_tracking import ApiUsageTracker

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
    """대시보드 요약 분석 데이터 (실데이터).
    - request_statistics, endpoint_usage_daily 등 집계 테이블을 사용
    - 데이터가 없을 경우 0 값으로 채워 반환
    """
    try:
        daily = []
        weekly = []
        monthly = []
        realtime = {
            "currentActiveUsers": 0,
            "requestsPerMinute": 0,
            "systemHealth": "healthy",
        }

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
        results = []
        
        # API 타입별 필터링 조건 설정
        api_filter = ""
        if api_type == "handwriting":
            api_filter = "AND path = '/api/handwriting-verify'"
        elif api_type == "abstract":
            api_filter = "AND path = '/api/abstract-verify'"
        elif api_type == "imagecaptcha":
            api_filter = "AND path = '/api/imagecaptcha-verify'"
        else:  # all
            api_filter = "AND path IN ('/api/handwriting-verify', '/api/abstract-verify', '/api/imagecaptcha-verify')"
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if period == "daily":
                    cursor.execute(
                        f"""
                        SELECT DATE(request_time) as date, 
                               COUNT(*) as total,
                               SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) as success,
                               SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as failed
                        FROM request_logs
                        WHERE request_time >= CURDATE() - INTERVAL 6 DAY
                        {api_filter}
                        GROUP BY DATE(request_time)
                        ORDER BY date ASC
                        """
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
                    cursor.execute(
                        f"""
                        SELECT YEARWEEK(request_time, 3) AS yw,
                               COUNT(*) AS total,
                               SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) AS success,
                               SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS failed
                        FROM request_logs
                        WHERE request_time >= CURDATE() - INTERVAL 28 DAY
                        {api_filter}
                        GROUP BY YEARWEEK(request_time, 3)
                        ORDER BY yw ASC
                        """
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
                    cursor.execute(
                        f"""
                        SELECT DATE_FORMAT(request_time, '%Y-%m') AS ym,
                               COUNT(*) AS total,
                               SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) AS success,
                               SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS failed
                        FROM request_logs
                        WHERE request_time >= (CURDATE() - INTERVAL 2 MONTH) - INTERVAL DAYOFMONTH(CURDATE())-1 DAY
                        {api_filter}
                        GROUP BY DATE_FORMAT(request_time, '%Y-%m')
                        ORDER BY ym ASC
                        """
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