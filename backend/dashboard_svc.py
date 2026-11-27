"""总览（含维保假绿闸）。

口径：维保屏不得刷成在线齐套。
- ``official_publications`` 只计「屏幕在线」的正式发布（维保屏不计入上屏）；
- ``suspended_publications`` 暴露遗留的「维保屏仍挂正式行」坏账；
- ``healthy`` 仅在无维保挂起时转真，总览灯与屏幕维保灯不得同时假绿。
"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import PRODUCT_META, connect

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        screens = conn.execute("SELECT COUNT(*) c FROM screens").fetchone()["c"]
        online = conn.execute("SELECT COUNT(*) c FROM screens WHERE status='online'").fetchone()["c"]
        maintenance = conn.execute(
            "SELECT COUNT(*) c FROM screens WHERE status='maintenance'"
        ).fetchone()["c"]
        assets = conn.execute("SELECT COUNT(*) c FROM assets WHERE status='ready'").fetchone()["c"]
        pubs = conn.execute(
            """
            SELECT COUNT(*) c FROM publications p
            JOIN screens s ON s.id=p.screen_id
            WHERE p.official=1 AND p.status='published' AND s.status <> 'maintenance'
            """
        ).fetchone()["c"]
        suspended = conn.execute(
            """
            SELECT COUNT(*) c FROM publications p
            JOIN screens s ON s.id=p.screen_id
            WHERE p.official=1 AND s.status='maintenance'
            """
        ).fetchone()["c"]
        shadows = conn.execute(
            "SELECT COUNT(*) c FROM publish_shadows WHERE status='open'"
        ).fetchone()["c"]
        panics = conn.execute("SELECT COUNT(*) c FROM panic_events").fetchone()["c"]
        overrides = conn.execute(
            "SELECT COUNT(*) c FROM overrides WHERE official=1 AND active=1"
        ).fetchone()["c"]
    return {
        "product": PRODUCT_META["name"],
        "domain": PRODUCT_META["domain"],
        "sub": PRODUCT_META["sub"],
        "skeleton": PRODUCT_META["skeleton"],
        "screens": screens,
        "online_screens": online,
        "maintenance_screens": maintenance,
        "ready_assets": assets,
        "official_publications": pubs,
        "suspended_publications": suspended,
        "open_shadows": shadows,
        "panic_events": panics,
        "active_overrides": overrides,
        "healthy": suspended == 0,
    }
