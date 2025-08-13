from fastapi import APIRouter, HTTPException, Query
from typing import List, Literal, Optional
from datetime import date, timedelta
from src.config.database import get_db_connection

router = APIRouter(prefix="/api", tags=["dashboard"])


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


@router.get("/dashboard/analytics")
def get_dashboard_analytics():
    """대시보드 요약 분석 데이터
    현재는 DB에 데이터가 없을 수 있으므로 간단한 가상/기본값 중심으로 반환
    """
    try:
        today = date.today()
        # 기본 7/4/3 구간 생성
        def build_series(days: int):
            return [
                {
                    "totalRequests": 1000 + i * 50,
                    "successfulSolves": 950 + i * 45,
                    "failedAttempts": 50 + i * 5,
                    "successRate": round(95.0 - i * 0.2, 1),
                    "averageResponseTime": 240 + (i % 5) * 5,
                }
                for i in range(days)
            ]

        return {
            "success": True,
            "data": {
                "dailyStats": build_series(7),
                "weeklyStats": build_series(4),
                "monthlyStats": build_series(3),
                "realtimeMetrics": {
                    "currentActiveUsers": 123,
                    "requestsPerMinute": 110,
                    "systemHealth": "healthy",
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analytics 수집 실패: {e}")


@router.get("/dashboard/stats")
def get_dashboard_stats(period: Literal["daily", "weekly", "monthly"] = Query("daily")):
    """기간별 캡차 통계
    실제 테이블 집계 전 기본 응답을 제공
    """
    try:
        length = 7 if period == "daily" else (4 if period == "weekly" else 3)
        items = [
            {
                "totalRequests": 1000 + i * 50,
                "successfulSolves": 950 + i * 45,
                "failedAttempts": 50 + i * 5,
                "successRate": round(95.0 - i * 0.2, 1),
                "averageResponseTime": 240 + (i % 5) * 5,
            }
            for i in range(length)
        ]
        return {"success": True, "data": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stats 수집 실패: {e}")


@router.get("/dashboard/realtime")
def get_realtime_metrics():
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
def get_captcha_performance():
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
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    status: Optional[Literal["success", "failed"]] = None,
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



from typing import List, Literal, Optional
from datetime import date, timedelta
from src.config.database import get_db_connection

router = APIRouter(prefix="/api", tags=["dashboard"])


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


@router.get("/dashboard/analytics")
def get_dashboard_analytics():
    """대시보드 요약 분석 데이터
    현재는 DB에 데이터가 없을 수 있으므로 간단한 가상/기본값 중심으로 반환
    """
    try:
        today = date.today()
        # 기본 7/4/3 구간 생성
        def build_series(days: int):
            return [
                {
                    "totalRequests": 1000 + i * 50,
                    "successfulSolves": 950 + i * 45,
                    "failedAttempts": 50 + i * 5,
                    "successRate": round(95.0 - i * 0.2, 1),
                    "averageResponseTime": 240 + (i % 5) * 5,
                }
                for i in range(days)
            ]

        return {
            "success": True,
            "data": {
                "dailyStats": build_series(7),
                "weeklyStats": build_series(4),
                "monthlyStats": build_series(3),
                "realtimeMetrics": {
                    "currentActiveUsers": 123,
                    "requestsPerMinute": 110,
                    "systemHealth": "healthy",
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analytics 수집 실패: {e}")


@router.get("/dashboard/stats")
def get_dashboard_stats(period: Literal["daily", "weekly", "monthly"] = Query("daily")):
    """기간별 캡차 통계
    실제 테이블 집계 전 기본 응답을 제공
    """
    try:
        length = 7 if period == "daily" else (4 if period == "weekly" else 3)
        items = [
            {
                "totalRequests": 1000 + i * 50,
                "successfulSolves": 950 + i * 45,
                "failedAttempts": 50 + i * 5,
                "successRate": round(95.0 - i * 0.2, 1),
                "averageResponseTime": 240 + (i % 5) * 5,
            }
            for i in range(length)
        ]
        return {"success": True, "data": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stats 수집 실패: {e}")


@router.get("/dashboard/realtime")
def get_realtime_metrics():
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
def get_captcha_performance():
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
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    status: Optional[Literal["success", "failed"]] = None,
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




