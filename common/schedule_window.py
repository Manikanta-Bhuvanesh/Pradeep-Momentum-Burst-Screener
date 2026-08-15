"""
Shared trading-window constants and time helpers, used by both
``run_scheduler.py`` (the scan loop, with or without Telegram) and
``telegram_bot/app.py`` (the ``/next_schedule`` command) so there's one
source of truth for "when does a scan run."

Window: 9:30 AM - 3:15 PM IST, every 15 minutes — chosen because a full
Nifty 500 fetch + all 4 setups' scans was measured end-to-end at ~52
seconds, comfortably under the interval (see run_scheduler.py's docstring).

Market holidays are NOT tracked here — only weekends are skipped.
"""
from __future__ import annotations

import math
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
WINDOW_START = dtime(9, 30)
WINDOW_END = dtime(15, 15)
INTERVAL_MINUTES = 15


def now_ist() -> datetime:
    return datetime.now(IST)


def today_at(day: datetime, t: dtime) -> datetime:
    return day.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def is_weekend(day: datetime) -> bool:
    return day.weekday() >= 5  # Sat=5, Sun=6


def next_scheduled_run(now: datetime | None = None) -> datetime:
    """
    The next time a scan is due, regardless of whether a scheduler process
    is actually running right now.
    """
    now = now or now_ist()

    if not is_weekend(now):
        ws = today_at(now, WINDOW_START)
        we = today_at(now, WINDOW_END)
        if now <= ws:
            return ws
        if now <= we:
            elapsed_min = (now - ws).total_seconds() / 60.0
            steps = math.ceil(elapsed_min / INTERVAL_MINUTES)
            candidate = ws + timedelta(minutes=INTERVAL_MINUTES * steps)
            if candidate <= we:
                return candidate
            # else: today's slots are exhausted, fall through to the next weekday

    d = now + timedelta(days=1)
    while is_weekend(d):
        d += timedelta(days=1)
    return today_at(d, WINDOW_START)
