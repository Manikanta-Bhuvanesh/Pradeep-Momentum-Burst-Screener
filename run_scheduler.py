"""
Self-scheduling entry point. Start this ONCE, manually — everything else is
automatic from here.

Two modes, chosen automatically based on whether TELEGRAM_BOT_TOKEN is set
in .env:

- **Telegram configured** (recommended — see README "Telegram bot"): runs
  the bot (on-demand /next_schedule, /today_signals, admin allowlist
  commands) AND the scan loop together in one process. The scan loop pushes
  a message with symbol/setup/note to every authorized user immediately
  after any run that finds a hit. Unlike the plain mode below, this runs
  INDEFINITELY — it sleeps through nights/weekends and resumes itself the
  next trading day, so the bot stays reachable for on-demand commands at any
  time (including outside market hours). Stop it with Ctrl+C.

- **Telegram not configured**: falls back to the original plain loop —
  start any time on a trading day, it waits for 9:30 AM IST if early, scans
  every 15 minutes until 3:15 PM IST, then exits. Start it again the next
  morning.

Why every 15 minutes: a full Nifty 500 scan across all 4 setups was timed
end-to-end at ~52 seconds (fetch ~46s + all 4 scans ~6s combined) — see
output/scheduler.log for the actual measured duration of every run. That's
comfortably under the 15-minute interval, so a fixed 15-min cadence from
9:30 AM to 3:15 PM IST is safe with no overlap risk.

Fully quiet — nothing is printed to the console. Check output/scheduler.log
for a record of every run and any warnings, and output/live_signals.csv /
output/archive/ for results.

Usage::

    python run_scheduler.py
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

from common.logging_setup import get_logger
from common.schedule_window import WINDOW_END, WINDOW_START, is_weekend, now_ist, today_at
from run_all_live_screens import run_all
from telegram_bot.config import load_telegram_config, telegram_configured

# The measured full run is ~1 minute; this is a generous safety ceiling for
# the warning below, not the actual expected duration.
SLOW_RUN_WARNING_MINUTES = 15

_log = get_logger()


def _run_plain_loop() -> None:
    """No Telegram: single trading day, exits after the 3:15 PM run."""
    now = now_ist()

    if is_weekend(now):
        _log.info(f"Scheduler started {now.isoformat()} on a weekend — NSE closed, exiting without running.")
        return

    window_start = today_at(now, WINDOW_START)
    window_end = today_at(now, WINDOW_END)

    if now > window_end:
        _log.info(f"Scheduler started {now.isoformat()}, past today's {WINDOW_END} close — nothing to do today.")
        return

    if now < window_start:
        wait_s = (window_start - now).total_seconds()
        _log.info(f"Scheduler started {now.isoformat()}, waiting {wait_s / 60:.1f} min for {WINDOW_START} open.")
        time.sleep(wait_s)

    _log.info(f"Scheduler running every 15 min until {WINDOW_END} IST (Telegram not configured).")

    while True:
        run_start = now_ist()
        try:
            run_all()
        except Exception:
            _log.exception("Scan run failed")
        run_end = now_ist()
        duration_s = (run_end - run_start).total_seconds()
        if duration_s > SLOW_RUN_WARNING_MINUTES * 60:
            _log.warning(
                f"Run took {duration_s / 60:.1f} min — longer than the {SLOW_RUN_WARNING_MINUTES}-min "
                "safety ceiling. The next run may be delayed or overlap."
            )

        next_run = run_start + timedelta(minutes=15)
        if next_run > window_end:
            _log.info(f"Next run ({next_run.time()}) would be past {WINDOW_END} — stopping for today.")
            return

        sleep_s = (next_run - now_ist()).total_seconds()
        if sleep_s > 0:
            time.sleep(sleep_s)


def main() -> None:
    if not telegram_configured():
        _log.info("TELEGRAM_BOT_TOKEN not set in .env — running the plain (non-Telegram) scheduler loop.")
        _run_plain_loop()
        return

    try:
        cfg = load_telegram_config()
    except RuntimeError as exc:
        _log.warning(f"Telegram config invalid ({exc}); falling back to the non-Telegram scheduler loop.")
        _run_plain_loop()
        return

    from telegram_bot.app import run_scheduler_with_bot

    try:
        asyncio.run(run_scheduler_with_bot(cfg))
    except KeyboardInterrupt:
        _log.info("Stopped by user (Ctrl+C).")


if __name__ == "__main__":
    main()
