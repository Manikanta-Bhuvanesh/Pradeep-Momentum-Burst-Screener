"""
Single consolidated live-signals CSV, shared by every setup.

- One file: ``output/live_signals.csv``. Every setup's ``run_live_screen()``
  merges its hits into this same file (keyed by ``setup`` + ``symbol``)
  instead of writing its own separate CSV.
- Re-running any setup (or all of them via ``run_all_live_screens.py``) any
  number of times through the day does NOT duplicate rows: a stock that
  reappears bumps ``times_seen`` and refreshes ``last_scan_time`` /
  ``trigger_date`` / ``trigger_close`` / ``note``, rather than adding a new
  row.
- Archiving is lazy, not a background job: the first run of a new calendar
  day detects that the existing file's rows are from an earlier day (via
  ``last_scan_time``), moves that file to
  ``output/archive/live_signals_<that day>.csv``, and starts today's file
  fresh. There is no scheduler here — this only fires the next time you
  actually run a screen.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .logging_setup import get_logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = _PROJECT_ROOT / "output"
ARCHIVE_DIR: Path = OUTPUT_DIR / "archive"
LIVE_SIGNALS_CSV: Path = OUTPUT_DIR / "live_signals.csv"

COLUMNS: list[str] = [
    "setup",
    "symbol",
    "times_seen",
    "first_scan_time",
    "last_scan_time",
    "trigger_date",
    "trigger_close",
    "note",
]


def _today_str() -> str:
    return date.today().isoformat()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def _archive(df: pd.DataFrame, day_str: str) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"live_signals_{day_str}.csv"
    df.to_csv(archive_path, index=False)
    get_logger().info(f"[archive] rolled over previous day's signals -> {archive_path}")


def _load_today() -> pd.DataFrame:
    """Today's rows from LIVE_SIGNALS_CSV — archiving it first if it's from an earlier day."""
    if not LIVE_SIGNALS_CSV.is_file():
        return _empty()
    try:
        existing = pd.read_csv(LIVE_SIGNALS_CSV)
    except pd.errors.EmptyDataError:
        return _empty()
    if existing.empty or "last_scan_time" not in existing.columns:
        return _empty()

    existing_dates = pd.to_datetime(existing["last_scan_time"], errors="coerce").dt.date
    most_recent = existing_dates.max()
    if most_recent is None:
        return _empty()
    if most_recent.isoformat() != _today_str():
        _archive(existing, most_recent.isoformat())
        return _empty()
    return existing


def merge_and_save(setup_name: str, hits: pd.DataFrame) -> pd.DataFrame:
    """
    Merge one setup's freshly-scanned hits into today's consolidated CSV and
    write the result. ``hits`` must have ``symbol``, ``trigger_date``,
    ``trigger_close``, ``note`` columns (as produced by each setup's
    ``run_live_screen``). Returns the full updated consolidated DataFrame.
    """
    today_df = _load_today()
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    rows = today_df.to_dict("records")
    index_lookup = {(r["setup"], r["symbol"]): i for i, r in enumerate(rows)}

    if hits is not None and not hits.empty:
        for _, hit in hits.iterrows():
            key = (setup_name, hit["symbol"])
            if key in index_lookup:
                i = index_lookup[key]
                rows[i]["times_seen"] = int(rows[i]["times_seen"]) + 1
                rows[i]["last_scan_time"] = now
                rows[i]["trigger_date"] = hit["trigger_date"]
                rows[i]["trigger_close"] = hit["trigger_close"]
                rows[i]["note"] = hit["note"]
            else:
                rows.append(
                    {
                        "setup": setup_name,
                        "symbol": hit["symbol"],
                        "times_seen": 1,
                        "first_scan_time": now,
                        "last_scan_time": now,
                        "trigger_date": hit["trigger_date"],
                        "trigger_close": hit["trigger_close"],
                        "note": hit["note"],
                    }
                )
                index_lookup[key] = len(rows) - 1

    updated = pd.DataFrame(rows, columns=COLUMNS)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    updated.to_csv(LIVE_SIGNALS_CSV, index=False)
    return updated
