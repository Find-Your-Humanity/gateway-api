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
            sets.append(f"{f} = %s")
            values.append(payload[f])

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
def delete_user(user_id: int = Path(..., ge=1)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
                affected = cursor.rowcount or 0
                conn.commit()
                if affected == 0:
                    raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "deleted": affected}
    except Exception as e:
        # 외래키 제약 등으로 삭제 실패 시 409로 반환
        msg = str(e)
        if "foreign key" in msg.lower() or "constraint" in msg.lower():
            raise HTTPException(status_code=409, detail="Cannot delete user due to related records")
        raise HTTPException(status_code=500, detail=msg)


