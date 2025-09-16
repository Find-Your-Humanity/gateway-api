"""
Suspicious IP 관리 API 엔드포인트
사용자별로 자신의 suspicious IP만 조회/관리할 수 있도록 구현
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Dict, Any, Optional
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Suspicious IP Management"])

@router.get("/suspicious-ips")
async def get_suspicious_ips(
    request: Request,
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(20, ge=1, le=100, description="페이지당 항목 수"),
    is_blocked: Optional[bool] = Query(None, description="차단 여부 필터")
):
    """
    사용자의 suspicious IP 목록을 조회합니다.
    각 API 키별로 자신의 데이터만 볼 수 있습니다.
    """
    try:
        # API 키에서 사용자 정보 추출
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # API 키로 사용자 정보 조회
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM api_keys WHERE key_id = %s", (api_key,))
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid API key")
                user_id = result["user_id"] if isinstance(result, dict) else result[0]
        
        offset = (page - 1) * limit
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자의 API 키 목록 조회
                cursor.execute("""
                    SELECT key_id FROM api_keys 
                    WHERE user_id = %s AND is_active = 1
                """, (user_id,))
                
                rows = cursor.fetchall()
                api_keys = [row["key_id"] if isinstance(row, dict) else row[0] for row in rows]
                
                if not api_keys:
                    return {
                        "suspicious_ips": [],
                        "total_count": 0,
                        "page": page,
                        "limit": limit,
                        "total_pages": 0
                    }
                
                # WHERE 조건 구성
                where_conditions = ["suspicious_ips.api_key IN (%s)" % ",".join(["%s"] * len(api_keys))]
                params = api_keys.copy()
                
                if is_blocked is not None:
                    where_conditions.append("is_blocked = %s")
                    params.append(is_blocked)
                
                where_clause = " AND ".join(where_conditions)
                logger.info(f"[suspicious-ips] where={where_clause} keys={len(api_keys)} blocked_filter={is_blocked}")
                
                # 총 개수 조회
                sql_count = f"SELECT COUNT(*) AS cnt FROM suspicious_ips WHERE {where_clause}"
                logger.info(f"[suspicious-ips] sql_count={sql_count} params={params}")
                cursor.execute(sql_count, params)
                _row = cursor.fetchone()
                total_count = (_row.get("cnt") if isinstance(_row, dict) else _row[0]) if _row else 0
                
                # 데이터 조회
                sql_list = (
                    f"SELECT id, api_key, ip_address, violation_count, first_violation_time, last_violation_time, "
                    f"is_blocked, block_reason, created_at, updated_at FROM suspicious_ips WHERE {where_clause} "
                    f"ORDER BY last_violation_time DESC LIMIT %s OFFSET %s"
                )
                list_params = params + [limit, offset]
                logger.info(f"[suspicious-ips] sql_list={sql_list} params={list_params}")
                cursor.execute(sql_list, list_params)
                
                suspicious_ips = []
                for row in cursor.fetchall():
                    if isinstance(row, dict):
                        suspicious_ips.append({
                            "id": row.get("id"),
                            "api_key": row.get("api_key"),
                            "ip_address": row.get("ip_address"),
                            "violation_count": row.get("violation_count"),
                            "first_violation_time": row.get("first_violation_time").isoformat() if row.get("first_violation_time") else None,
                            "last_violation_time": row.get("last_violation_time").isoformat() if row.get("last_violation_time") else None,
                            "is_blocked": bool(row.get("is_blocked")),
                            "block_reason": row.get("block_reason"),
                            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
                            "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
                        })
                    else:
                        suspicious_ips.append({
                            "id": row[0],
                            "api_key": row[1],
                            "ip_address": row[2],
                            "violation_count": row[3],
                            "first_violation_time": row[4].isoformat() if row[4] else None,
                            "last_violation_time": row[5].isoformat() if row[5] else None,
                            "is_blocked": bool(row[6]),
                            "block_reason": row[7],
                            "created_at": row[8].isoformat() if row[8] else None,
                            "updated_at": row[9].isoformat() if row[9] else None,
                        })
                
                total_pages = (total_count + limit - 1) // limit
                
                return {
                    "suspicious_ips": suspicious_ips,
                    "total_count": total_count,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages
                }
                
    except Exception as e:
        logger.exception(f"Failed to get suspicious IPs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/ip-stats")
async def get_ip_stats(request: Request):
    """
    사용자의 IP 위반 통계를 조회합니다.
    """
    try:
        # API 키에서 사용자 정보 추출
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # API 키로 사용자 정보 조회
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM api_keys WHERE key_id = %s", (api_key,))
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid API key")
                user_id = result["user_id"] if isinstance(result, dict) else result[0]
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자의 API 키 목록 조회
                cursor.execute("""
                    SELECT key_id FROM api_keys 
                    WHERE user_id = %s AND is_active = 1
                """, (user_id,))
                
                rows = cursor.fetchall()
                api_keys = [row["key_id"] if isinstance(row, dict) else row[0] for row in rows]
                
                if not api_keys:
                    return {
                        "total_suspicious_ips": 0,
                        "blocked_ips": 0,
                        "active_suspicious_ips": 0,
                        "recent_violations_24h": 0,
                        "api_key_stats": []
                    }
                
                # 전체 통계 조회
                sql_total = """
                    SELECT 
                        COUNT(*) as total_suspicious_ips,
                        SUM(CASE WHEN is_blocked = 1 THEN 1 ELSE 0 END) as blocked_ips,
                        SUM(CASE WHEN is_blocked = 0 THEN 1 ELSE 0 END) as active_suspicious_ips,
                        SUM(CASE WHEN last_violation_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 ELSE 0 END) as recent_violations_24h
                    FROM suspicious_ips 
                    WHERE suspicious_ips.api_key IN (%s)
                """ % ",".join(["%s"] * len(api_keys))
                logger.info(f"[ip-stats] sql_total={sql_total} keys={len(api_keys)}")
                cursor.execute(sql_total, api_keys)
                
                stats = cursor.fetchone() or {}
                
                # API 키별 통계 조회
                sql_by_key = """
                    SELECT 
                        api_key,
                        COUNT(*) as total_suspicious_ips,
                        SUM(CASE WHEN is_blocked = 1 THEN 1 ELSE 0 END) as blocked_ips,
                        SUM(CASE WHEN is_blocked = 0 THEN 1 ELSE 0 END) as active_suspicious_ips,
                        SUM(CASE WHEN last_violation_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 ELSE 0 END) as recent_violations_24h
                    FROM suspicious_ips 
                    WHERE suspicious_ips.api_key IN (%s)
                    GROUP BY api_key
                    ORDER BY total_suspicious_ips DESC
                """ % ",".join(["%s"] * len(api_keys))
                logger.info(f"[ip-stats] sql_by_key={sql_by_key}")
                cursor.execute(sql_by_key, api_keys)
                
                api_key_stats = []
                for row in cursor.fetchall():
                    if isinstance(row, dict):
                        api_key_stats.append({
                            "api_key": row.get("api_key"),
                            "total_suspicious_ips": row.get("total_suspicious_ips", 0),
                            "blocked_ips": row.get("blocked_ips", 0),
                            "active_suspicious_ips": row.get("active_suspicious_ips", 0),
                            "recent_violations_24h": row.get("recent_violations_24h", 0),
                        })
                    else:
                        api_key_stats.append({
                            "api_key": row[0],
                            "total_suspicious_ips": row[1],
                            "blocked_ips": row[2],
                            "active_suspicious_ips": row[3],
                            "recent_violations_24h": row[4],
                        })
                
                if isinstance(stats, dict):
                    total = stats.get("total_suspicious_ips", 0) or 0
                    blocked = stats.get("blocked_ips", 0) or 0
                    active = stats.get("active_suspicious_ips", 0) or 0
                    recent = stats.get("recent_violations_24h", 0) or 0
                else:
                    total = (stats[0] if len(stats) > 0 else 0) or 0
                    blocked = (stats[1] if len(stats) > 1 else 0) or 0
                    active = (stats[2] if len(stats) > 2 else 0) or 0
                    recent = (stats[3] if len(stats) > 3 else 0) or 0

                return {
                    "total_suspicious_ips": total,
                    "blocked_ips": blocked,
                    "active_suspicious_ips": active,
                    "recent_violations_24h": recent,
                    "api_key_stats": api_key_stats,
                }
                
    except Exception as e:
        logger.exception(f"Failed to get IP stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/block-ip")
async def block_ip(
    request: Request,
    ip_address: str,
    reason: str = "Manual block"
):
    """
    특정 IP를 차단합니다.
    """
    try:
        # API 키에서 사용자 정보 추출
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # API 키로 사용자 정보 조회
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM api_keys WHERE key_id = %s", (api_key,))
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid API key")
                user_id = result["user_id"] if isinstance(result, dict) else result[0]
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자의 API 키 목록 조회
                cursor.execute("""
                    SELECT key_id FROM api_keys 
                    WHERE user_id = %s AND is_active = 1
                """, (user_id,))
                
                rows = cursor.fetchall()
                api_keys = [row["key_id"] if isinstance(row, dict) else row[0] for row in rows]
                
                if not api_keys:
                    raise HTTPException(status_code=404, detail="No API keys found")
                
                # IP 차단 업데이트
                cursor.execute("""
                    UPDATE suspicious_ips 
                    SET is_blocked = 1, block_reason = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE ip_address = %s AND api_key IN (%s)
                """ % ("%s,%s," + ",".join(["%s"] * len(api_keys))), 
                [reason, ip_address] + api_keys)
                
                affected_rows = cursor.rowcount
                
                if affected_rows == 0:
                    raise HTTPException(status_code=404, detail="IP not found or not accessible")
                
                conn.commit()
                
                return {
                    "message": f"IP {ip_address} blocked successfully",
                    "affected_rows": affected_rows
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to block IP {ip_address}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/unblock-ip")
async def unblock_ip(
    request: Request,
    ip_address: str
):
    """
    특정 IP의 차단을 해제합니다.
    """
    try:
        # API 키에서 사용자 정보 추출
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # API 키로 사용자 정보 조회
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM api_keys WHERE api_key = %s", (api_key,))
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid API key")
                user_id = result["user_id"] if isinstance(result, dict) else result[0]
        
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 사용자의 API 키 목록 조회
                cursor.execute("""
                    SELECT api_key FROM api_keys 
                    WHERE user_id = %s AND is_active = 1
                """, (user_id,))
                
                rows = cursor.fetchall()
                api_keys = [row["api_key"] if isinstance(row, dict) else row[0] for row in rows]
                
                if not api_keys:
                    raise HTTPException(status_code=404, detail="No API keys found")
                
                # IP 차단 해제
                cursor.execute("""
                    UPDATE suspicious_ips 
                    SET is_blocked = 0, block_reason = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE ip_address = %s AND api_key IN (%s)
                """ % ("%s," + ",".join(["%s"] * len(api_keys))), 
                [ip_address] + api_keys)
                
                affected_rows = cursor.rowcount
                
                if affected_rows == 0:
                    raise HTTPException(status_code=404, detail="IP not found or not accessible")
                
                conn.commit()
                
                return {
                    "message": f"IP {ip_address} unblocked successfully",
                    "affected_rows": affected_rows
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unblock IP {ip_address}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
