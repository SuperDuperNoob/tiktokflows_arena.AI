"""Timezone and time utilities."""

import os
from datetime import date, datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # py < 3.9
    ZoneInfo = None  # type: ignore[assignment]

from services.infrastructure.config import cfg


# MYT timezone offset (UTC+8).
MYT_OFFSET = timedelta(hours=8)
MYT = timezone(MYT_OFFSET)

TIMEZONE = os.environ.get("TIKTOKFLOW_TZ") or \
    cfg("timezone", "tz", default="Asia/Kuala_Lumpur") or "Asia/Kuala_Lumpur"

OWN_HANDLE = (os.environ.get("TIKTOK_SESSION_USER")
              or cfg("tiktok", "session_username") or "kumpul.shop").lower()
RIVAL_HANDLE = (os.environ.get("TIKTOK_RIVAL_HANDLE")
                or cfg("analytics", "rival_handle")
                or "reski.reski700").lower()


def local_tz():
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return None


def local_now() -> datetime:
    return datetime.now(local_tz())


def local_today() -> date:
    return local_now().date()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp(dt: datetime | None = None) -> str:
    dt = dt or local_now()
    label = TIMEZONE if dt.tzinfo else f"{TIMEZONE}?"
    return f"{dt.strftime('%Y-%m-%d %H:%M')} {label}"


def human(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"