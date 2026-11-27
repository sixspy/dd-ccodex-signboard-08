"""发布上屏（甲口径：维保屏正式整笔拒写、正式册零增）。

「维保屏幕禁止正式上屏」：
- 屏幕状态为维保时，正式发布整笔拒写（不升版本、不落审计、不写历史成功记录）；
- 与「同屏维保发布互斥」（``maint_publish:{screen_id}``）共用同一把锁，
  发布与屏幕维保切换不能交错，杜绝「维保已生效但仍落正式发布」的双成态；
- 乙路径（影子草案）在维保态同样拒收，两路不得混用，也不另开第三路。
"""
from __future__ import annotations

import time
import uuid
from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_audit, write_history
from auth import current_user, require_writer
from db import connect, rows_to_list
from locks import acquire, mutex_key, release
from policies import assert_playlist_ready, assert_screen_online, assert_window_open
from validators import require_positive_int, require_title

router = APIRouter(prefix="/api/publish", tags=["publish"])


@router.get("/official")
def list_official(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                """
                SELECT p.*, s.code screen_code, s.title screen_title, s.status screen_status,
                       pl.code playlist_code, w.code window_code
                FROM publications p
                JOIN screens s ON s.id=p.screen_id
                JOIN playlists pl ON pl.id=p.playlist_id
                JOIN time_windows w ON w.id=p.window_id
                WHERE p.official=1
                ORDER BY p.id DESC
                """
            ).fetchall()
        )
    for r in rows:
        # 遗留/旁路写入的维保屏正式行：显式标挂起，不得伪装成已上屏。
        r["suspended"] = r["screen_status"] == "maintenance"
    return {"items": rows}


@router.get("/shadows")
def list_shadows(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                """
                SELECT sh.*, s.code screen_code, pl.code playlist_code, w.code window_code
                FROM publish_shadows sh
                JOIN screens s ON s.id=sh.screen_id
                JOIN playlists pl ON pl.id=sh.playlist_id
                JOIN time_windows w ON w.id=sh.window_id
                ORDER BY sh.id DESC
                """
            ).fetchall()
        )
    return {"items": rows}


def _load_refs(conn, screen_id, playlist_id, window_id):
    screen = conn.execute("SELECT * FROM screens WHERE id=?", (screen_id,)).fetchone()
    playlist = conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
    window = conn.execute("SELECT * FROM time_windows WHERE id=?", (window_id,)).fetchone()
    if not screen or not playlist or not window:
        raise HTTPException(404, "屏幕/清单/时段窗不存在")
    assert_screen_online(screen["status"])
    assert_playlist_ready(playlist["status"])
    assert_window_open(window["status"])
    return screen, playlist, window


@router.post("/official")
def publish_official(body: dict, authorization: str | None = Header(default=None)):
    """甲路径：同事务写入正式发布并升版本；维保屏整笔拒写。"""
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    playlist_id = require_positive_int(body.get("playlist_id"), "清单编号")
    window_id = require_positive_int(body.get("window_id"), "时段编号")
    summary = require_title(body.get("summary") or "正式发布", "发布摘要")
    layout_id = body.get("layout_id")
    lock_key = mutex_key(screen_id)
    acquire(lock_key, user["username"])
    try:
        with connect() as conn:
            _load_refs(conn, screen_id, playlist_id, window_id)
            prev = conn.execute(
                "SELECT version FROM publications WHERE screen_id=? AND official=1",
                (screen_id,),
            ).fetchone()
            version = (prev["version"] + 1) if prev else 1
            conn.execute("DELETE FROM publications WHERE screen_id=? AND official=1", (screen_id,))
            cur = conn.execute(
                "INSERT INTO publications(screen_id,playlist_id,window_id,layout_id,version,summary,status,official,published_at,published_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    screen_id,
                    playlist_id,
                    window_id,
                    layout_id,
                    version,
                    summary,
                    "published",
                    1,
                    time.time(),
                    user["username"],
                ),
            )
            pid = cur.lastrowid
            conn.commit()
        write_history("publication", pid, "publish_official", summary, user["username"])
        write_audit(user["username"], "publish.official", {"id": pid, "version": version})
        return {"id": pid, "version": version, "path": "official"}
    finally:
        release(lock_key, user["username"])


@router.post("/shadow")
def create_shadow(body: dict, authorization: str | None = Header(default=None)):
    """乙路径第一步：只写影子草案，正式区零改（维保态同样拒收）。"""
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    playlist_id = require_positive_int(body.get("playlist_id"), "清单编号")
    window_id = require_positive_int(body.get("window_id"), "时段编号")
    summary = require_title(body.get("summary") or "影子发布草案", "发布摘要")
    layout_id = body.get("layout_id")
    with connect() as conn:
        _load_refs(conn, screen_id, playlist_id, window_id)
        cur = conn.execute(
            "INSERT INTO publish_shadows(screen_id,playlist_id,window_id,layout_id,summary,status,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)",
            (
                screen_id,
                playlist_id,
                window_id,
                layout_id,
                summary,
                "open",
                time.time(),
                user["username"],
            ),
        )
        sid = cur.lastrowid
        conn.commit()
    write_history("publish_shadow", sid, "create", summary, user["username"])
    return {"id": sid, "path": "shadow", "status": "open"}


@router.post("/shadow/{shadow_id}/promote")
def promote_shadow(shadow_id: int, authorization: str | None = Header(default=None)):
    """乙路径升正：原子落正式区（仍受维保闸约束）。"""
    user = current_user(authorization)
    require_writer(user)
    with connect() as conn:
        sh = conn.execute("SELECT * FROM publish_shadows WHERE id=?", (shadow_id,)).fetchone()
        if not sh:
            raise HTTPException(404, "影子不存在")
        if sh["status"] != "open":
            raise HTTPException(409, "影子不可升正")
        screen_id = sh["screen_id"]
    lock_key = mutex_key(screen_id)
    acquire(lock_key, user["username"])
    try:
        with connect() as conn:
            sh = conn.execute("SELECT * FROM publish_shadows WHERE id=?", (shadow_id,)).fetchone()
            _load_refs(conn, sh["screen_id"], sh["playlist_id"], sh["window_id"])
            prev = conn.execute(
                "SELECT version FROM publications WHERE screen_id=? AND official=1",
                (sh["screen_id"],),
            ).fetchone()
            version = (prev["version"] + 1) if prev else 1
            conn.execute("DELETE FROM publications WHERE screen_id=? AND official=1", (sh["screen_id"],))
            cur = conn.execute(
                "INSERT INTO publications(screen_id,playlist_id,window_id,layout_id,version,summary,status,official,published_at,published_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    sh["screen_id"],
                    sh["playlist_id"],
                    sh["window_id"],
                    sh["layout_id"],
                    version,
                    sh["summary"],
                    "published",
                    1,
                    time.time(),
                    user["username"],
                ),
            )
            pid = cur.lastrowid
            conn.execute(
                "UPDATE publish_shadows SET status='promoted' WHERE id=?",
                (shadow_id,),
            )
            conn.commit()
        write_history("publication", pid, "promote_shadow", f"升正影子 {shadow_id}", user["username"])
        write_audit(user["username"], "publish.promote", {"shadow_id": shadow_id, "id": pid})
        return {"id": pid, "version": version, "path": "shadow_promote"}
    finally:
        release(lock_key, user["username"])


@router.post("/race_maint_block")
def race_maint_block(body: dict, authorization: str | None = Header(default=None)):
    """争用演练入口：同屏两路抢「同屏维保发布互斥」，胜方落地维保拦截，败方只留痕。

    ``hold_ms`` 用于放大争用窗口（仅演练口，0～3000ms），使双请求确实交错。
    """
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    reason = require_title(body.get("reason") or "维保禁发拦截", "原因")
    hold_ms = require_positive_int(body.get("hold_ms") or 1, "持锁毫秒", 1, 3000)
    lock_key = mutex_key(screen_id)
    acquire(lock_key, user["username"])
    try:
        # 争用窗口：持锁片刻，让并发请求在锁内相遇（失败方只留痕，不改业务态）。
        time.sleep(hold_ms / 1000.0)
        with connect() as conn:
            screen = conn.execute("SELECT * FROM screens WHERE id=?", (screen_id,)).fetchone()
            if not screen:
                raise HTTPException(404, "屏幕不存在")
            conn.execute("UPDATE screens SET status='maintenance' WHERE id=?", (screen_id,))
            withdrawn = conn.execute(
                "SELECT id FROM publications WHERE screen_id=? AND official=1", (screen_id,)
            ).fetchall()
            conn.execute("DELETE FROM publications WHERE screen_id=? AND official=1", (screen_id,))
            conn.commit()
        write_history("screen", screen_id, "maintenance_enter", f"维保拦截：{reason}", user["username"])
        for row in withdrawn:
            write_history("publication", row["id"], "withdraw_maintenance", reason, user["username"])
        write_audit(user["username"], "publish.race_maint_block", {"screen_id": screen_id})
        return {"ok": True, "screen_id": screen_id, "withdrawn": len(withdrawn)}
    finally:
        release(lock_key, user["username"])
