"""变更历史（同源可追溯）。

维保口径相关动作（同源可查）：
- ``screen/maintenance_enter``：屏幕转入维保；
- ``publication/withdraw_maintenance``：维保撤下正式发布；
- ``lock/contention``：同屏维保发布互斥争用败方留痕。
"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import connect, rows_to_list

router = APIRouter(prefix="/api/history", tags=["history"])

ACTION_LABEL = {
    "maintenance_enter": "转入维保",
    "withdraw_maintenance": "维保撤下正式",
    "contention": "互斥争用",
}


@router.get("")
def list_history(limit: int = 100, authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                "SELECT * FROM change_history ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 300)),),
            ).fetchall()
        )
    for r in rows:
        r["action_label"] = ACTION_LABEL.get(r["action"], r["action"])
    return {"items": rows}
