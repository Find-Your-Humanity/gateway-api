from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional, List, Dict, Any
from src.config.database import get_db_connection

router = APIRouter()


def _row_to_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "username": row.get("username"),
        "name": row.get("name"),
        "contact": row.get("contact"),
        "is_active": bool(row.get("is_active")),
        "is_admin": bool(row.get("is_admin")),
        "created_at": row.get("created_at"),
    }


def _as_int_bool(value: Any) -> Optional[int]:
    # None은 그대로 유지
    if value is None:
        return None
    # 이미 정수 0/1이면 그대로
    if isinstance(value, int):
        return 1 if value != 0 else 0
    # 불리언 처리
    if isinstance(value, bool):
        return 1 if value else 0
    # 문자열 처리: '1','true','True','yes','on' => 1, '0','false','no','off' => 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("1", "true", "yes", "on"):  # 활성
            return 1
        if v in ("0", "false", "no", "off"):  # 비활성
            return 0
    # 기타 타입은 파이썬 truthy로 변환
    return 1 if value else 0


@router.get("/api/admin/users")
def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None)
):
    offset = (page - 1) * limit
    users: List[Dict[str, Any]] = []
    total = 0
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                params: List[Any] = []
                where = ""
                if search:
                    where = "WHERE email LIKE %s OR username LIKE %s OR name LIKE %s"
                    like = f"%{search}%"
                    params.extend([like, like, like])

                count_sql = f"SELECT COUNT(*) AS cnt FROM users {where}"
                cursor.execute(count_sql, params)
                total = int((cursor.fetchone() or {}).get("cnt", 0))

                sql = (
                    "SELECT id, email, username, name, contact, is_active, is_admin, created_at "
                    f"FROM users {where} ORDER BY id DESC LIMIT %s OFFSET %s"
                )
                cursor.execute(sql, params + [limit, offset])
                for row in cursor.fetchall() or []:
                    users.append(_row_to_user(row))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pages = (total + limit - 1) // limit if limit else 1
    return {
        "success": True,
        "data": {
            "data": users,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": pages,
            },
        },
    }


@router.put("/api/admin/users/{user_id}")
def update_user(
    user_id: int = Path(..., ge=1),
    payload: Dict[str, Any] = None,
):
    if payload is None:
        payload = {}

    allowed_fields = ["email", "username", "name", "contact", "is_active", "is_admin"]
    sets: List[str] = []
    values: List[Any] = []
    for f in allowed_fields:
        if f in payload and payload[f] is not None:
            val = payload[f]
            if f in ("is_active", "is_admin"):
                val = _as_int_bool(val)
            sets.append(f"{f} = %s")
            values.append(val)

    if not sets:
        return {"success": True, "data": None}

    values.append(user_id)
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                sql = f"UPDATE users SET {', '.join(sets)} WHERE id = %s"
                cursor.execute(sql, values)
                conn.commit()

                cursor.execute(
                    "SELECT id, email, username, name, contact, is_active, is_admin, created_at FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="User not found")
                return {"success": True, "data": _row_to_user(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/admin/users/{user_id}")
def delete_user(
    user_id: int = Path(..., ge=1),
    force: bool = Query(False)
):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if force:
                    # 연관 데이터 정리 (제약으로 막히는 테이블 우선)
                    cursor.execute("DELETE FROM user_subscriptions WHERE user_id = %s", (user_id,))
                    cursor.execute("DELETE FROM payment_logs WHERE user_id = %s", (user_id,))
                    # 기타 토큰류/세션류는 CASCADE 또는 자체 정리 로직 존재
                    conn.commit()

                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
                affected = cursor.rowcount or 0
                conn.commit()
                if affected == 0:
                    raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "deleted": affected}
    except Exception as e:
        msg = str(e)
        if "foreign key" in msg.lower() or "constraint" in msg.lower():
            raise HTTPException(status_code=409, detail="Cannot delete user due to related records")
        raise HTTPException(status_code=500, detail=msg)


@router.patch("/api/admin/users/{user_id}/active")
def toggle_user_active(
    user_id: int = Path(..., ge=1),
    payload: Optional[Dict[str, Any]] = None,
):
    # payload에 is_active가 오면 해당 값으로 설정, 없으면 토글
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                # 현재 값 조회
                cursor.execute(
                    "SELECT is_active FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="User not found")

                current_active = bool(row.get("is_active"))
                if payload and "is_active" in payload and payload["is_active"] is not None:
                    new_active_int = _as_int_bool(payload["is_active"])
                else:
                    new_active_int = 0 if current_active else 1

                cursor.execute(
                    "UPDATE users SET is_active = %s WHERE id = %s",
                    (new_active_int, user_id),
                )
                conn.commit()

                cursor.execute(
                    "SELECT id, email, username, name, contact, is_active, is_admin, created_at FROM users WHERE id = %s",
                    (user_id,),
                )
                updated = cursor.fetchone()
                return {"success": True, "data": _row_to_user(updated)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


