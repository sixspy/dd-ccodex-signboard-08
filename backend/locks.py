"""写入短锁，防并发双写。

互斥键「同屏维保发布互斥」= ``maint_publish:{screen_id}``，发布服务与屏幕服务共用。
抢锁走 ``BEGIN IMMEDIATE``，取锁判定与落锁在同一事务内，杜绝「查无锁→双插」的无锁双成；
败方不写业务状态，只在变更历史留一条 ``lock/contention`` 争用痕迹。
"""
from __future__ import annotations

import time
from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_history
from auth import current_user, require_writer
from db import connect

router = APIRouter(prefix="/api/locks", tags=["locks"])

# 「同屏维保发布互斥」键前缀：发布、屏幕维保切换、争用演练共用同一把锁。
MAINT_PUBLISH_MUTEX = "maint_publish"


def mutex_key(screen_id: int) -> str:
    return f"{MAINT_PUBLISH_MUTEX}:{screen_id}"


def _entity_id(lock_key: str) -> int:
    tail = lock_key.rsplit(":", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return 0


def acquire(lock_key: str, holder: str, ttl_sec: int = 20) -> None:
    """原子抢锁；被占则留争用痕迹并抛 409，绝不动业务表。"""
    now = time.time()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT holder, expires_at FROM write_locks WHERE lock_key=?",
            (lock_key,),
        ).fetchone()
        if row and row["expires_at"] > now and row["holder"] != holder:
            held = row["holder"]
            conn.rollback()
            try:
                conn.close()
            except Exception:
                pass
            write_history(
                "lock",
                _entity_id(lock_key),
                "contention",
                f"同屏维保发布互斥争用 {lock_key}；持有者 {held}；请求者 {holder}",
                holder,
            )
            raise HTTPException(409, f"资源锁定中：{held}")
        conn.execute(
            "INSERT INTO write_locks(lock_key,holder,expires_at) VALUES(?,?,?) "
            "ON CONFLICT(lock_key) DO UPDATE SET holder=excluded.holder, expires_at=excluded.expires_at",
            (lock_key, holder, now + ttl_sec),
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def release(lock_key: str, holder: str) -> None:
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM write_locks WHERE lock_key=? AND holder=?",
            (lock_key, holder),
        )
        conn.commit()
    finally:
        conn.close()


@router.post("/acquire")
def api_acquire(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    key = (body.get("lock_key") or "").strip()
    if not key:
        raise HTTPException(400, "缺少 lock_key")
    acquire(key, user["username"], int(body.get("ttl_sec") or 20))
    return {"ok": True, "lock_key": key, "holder": user["username"]}


@router.post("/release")
def api_release(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    key = (body.get("lock_key") or "").strip()
    release(key, user["username"])
    return {"ok": True}
