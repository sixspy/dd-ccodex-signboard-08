"""屏幕台账。

维保口径（甲）：
- 屏幕转入维保时，同事务撤下其正式发布（跨表账实同事务），并记 ``maintenance_enter``；
- 维保切换与正式发布共用「同屏维保发布互斥」（``maint_publish:{screen_id}``），不能交错；
- 台账读取侧给出 ``publishable`` / ``on_air`` / ``official_suspended``，
  遗留的维保屏正式行标挂起，屏幕页与发布册不得同时假绿。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_audit, write_history
from auth import current_user, require_writer
from db import connect, rows_to_list
from locks import acquire, mutex_key, release
from models import SCREEN_STATUS_LABEL, ZONE_TYPE_LABEL
from validators import require_code, require_screen_status, require_title

router = APIRouter(prefix="/api/screens", tags=["screens"])


def _read_state(row: dict) -> dict:
    """发布态派生：维保屏不可发布、不上屏；正式行只标挂起不改账。"""
    maintenance = row["status"] == "maintenance"
    has_official = bool(row.get("official_count"))
    row["publishable"] = not maintenance
    row["official_suspended"] = maintenance and has_official
    row["on_air"] = (not maintenance) and has_official
    return row


@router.get("")
def list_screens(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, z.code zone_code, z.title zone_title, z.zone_type, z.risk_level,
                   (SELECT COUNT(*) FROM publications p
                     WHERE p.screen_id=s.id AND p.official=1) official_count
            FROM screens s JOIN zones z ON z.id=s.zone_id
            ORDER BY s.id
            """
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["status_label"] = SCREEN_STATUS_LABEL.get(d["status"], d["status"])
        d["zone_type_label"] = ZONE_TYPE_LABEL.get(d["zone_type"], d["zone_type"])
        items.append(_read_state(d))
    return {"items": items}


@router.post("")
def create_screen(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    code = require_code(body.get("code"), "屏幕编码")
    title = require_title(body.get("title"), "屏幕标题")
    status = require_screen_status(body.get("status") or "offline")
    resolution = (body.get("resolution") or "1920x1080").strip()
    orientation = body.get("orientation") or "landscape"
    zone_code = (body.get("zone_code") or "").strip()
    with connect() as conn:
        zone = conn.execute("SELECT * FROM zones WHERE code=?", (zone_code,)).fetchone()
        if not zone:
            raise HTTPException(404, "分区不存在")
        try:
            cur = conn.execute(
                "INSERT INTO screens(code,title,zone_id,resolution,status,orientation,note) VALUES(?,?,?,?,?,?,?)",
                (code, title, zone["id"], resolution, status, orientation, body.get("note") or ""),
            )
            sid = cur.lastrowid
            conn.commit()
        except Exception as exc:
            raise HTTPException(409, f"屏幕编码冲突: {exc}") from exc
    write_history("screen", sid, "create", f"登记屏幕 {code}", user["username"])
    write_audit(user["username"], "screen.create", {"id": sid, "code": code})
    return {"id": sid, "code": code}


@router.patch("/{screen_id}")
def patch_screen(screen_id: int, body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    with connect() as conn:
        row = conn.execute("SELECT * FROM screens WHERE id=?", (screen_id,)).fetchone()
        if not row:
            raise HTTPException(404, "屏幕不存在")
        status = require_screen_status(body.get("status", row["status"]))
        title = require_title(body.get("title", row["title"]), "屏幕标题")
        note = body.get("note", row["note"])
    entering_maint = status == "maintenance" and row["status"] != "maintenance"

    # 进入维保须与正式发布互斥：同锁下撤下正式册，避免与发布交错双成。
    lock_key = mutex_key(screen_id)
    if entering_maint:
        acquire(lock_key, user["username"])
    try:
        with connect() as conn:
            conn.execute(
                "UPDATE screens SET title=?, status=?, note=? WHERE id=?",
                (title, status, note, screen_id),
            )
            withdrawn: list[int] = []
            if entering_maint:
                withdrawn = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM publications WHERE screen_id=? AND official=1",
                        (screen_id,),
                    ).fetchall()
                ]
                conn.execute(
                    "DELETE FROM publications WHERE screen_id=? AND official=1",
                    (screen_id,),
                )
            conn.commit()
    finally:
        if entering_maint:
            release(lock_key, user["username"])

    if entering_maint:
        write_history("screen", screen_id, "maintenance_enter", f"屏幕状态={status}", user["username"])
        for pid in withdrawn:
            write_history("publication", pid, "withdraw_maintenance", "维保撤下正式发布", user["username"])
        write_audit(user["username"], "screen.maintenance_enter", {"id": screen_id, "withdrawn": len(withdrawn)})
    else:
        write_history("screen", screen_id, "patch", f"屏幕状态={status}", user["username"])
    return {"ok": True, "withdrawn": len(withdrawn) if entering_maint else 0}
