"""
Run all 4 setups' live screens in one go, fetching the Nifty 500 universe
ONCE and reusing it across all 4 scans (all 4 setups scan the same
universe now — see Algorithms/bottom_bounce/settings.py for why Bottom
Bounce's old Nifty-200-only restriction was dropped).

Fully quiet on stdout by default — nothing is printed to the console beyond
tqdm's own progress bars (fetch + each setup's scan), which ARE shown so the
terminal gives live feedback during a run. Structured events still go to
output/scheduler.log regardless. See common/logging_setup.py.

All 4 setups write into the SAME consolidated file, ``output/
live_signals.csv`` (columns: setup, symbol, times_seen, first_scan_time,
last_scan_time, trigger_date, trigger_close, note). A stock that reappears
on a later run in the same day does not get a duplicate row — ``times_seen``
increments instead. The first run of a new calendar day archives the
previous day's file to ``output/archive/`` and starts fresh — see
``common/signal_store.py``.

``run_all()`` also returns this run's NEWLY-first-seen-today hits
separately (not the day's cumulative totals, and NOT simply "whatever
matched this run") — a (setup, symbol) pair that already has ``times_seen
>= 1`` from an earlier run today is excluded even if it still matches, so
``run_scheduler.py`` / the Telegram bot push each stock+setup at most once
per calendar day, however many scheduled or /run_now runs still find it.
``times_seen`` in the CSV keeps incrementing regardless, for tracking.

``on_progress``, if given, is called with a plain status string at a few
points (start of fetch, fetch progress, start of each setup's scan) — used
by the Telegram bot to mirror progress into a live-edited message. Not
needed for terminal use (tqdm already covers that).

Usage::

    python run_all_live_screens.py
"""
from __future__ import annotations

import time
from typing import Callable

import pandas as pd

from common import market, signal_store
from common.logging_setup import get_logger
from common.universe_data import fetch_universe_ohlcv

from Algorithms.anticipation.runner import scan as scan_anticipation
from Algorithms.bottom_bounce.runner import scan as scan_bottom_bounce
from Algorithms.consolidation_breakout.runner import scan as scan_consolidation_breakout
from Algorithms.continuation.runner import scan as scan_continuation

_log = get_logger()

_SCANS = {
    "bottom_bounce": scan_bottom_bounce,
    "consolidation_breakout": scan_consolidation_breakout,
    "continuation": scan_continuation,
    "anticipation": scan_anticipation,
}

_HITS_COLUMNS = ["setup", "symbol", "trigger_date", "trigger_close", "note"]


def run_all(on_progress: Callable[[str], None] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (today's full consolidated table, this run's first-seen-today hits only)."""
    t0 = time.monotonic()
    n500 = market.load_nifty500()
    symbols = n500["symbol"].tolist()

    def _fetch_progress(completed: int, total: int) -> None:
        if on_progress is not None:
            on_progress(f"Fetching Nifty 500 data... {completed}/{total}")

    if on_progress is not None:
        on_progress(f"Fetching Nifty 500 data... 0/{len(symbols)}")
    universe_ohlcv = fetch_universe_ohlcv(
        symbols, on_progress=_fetch_progress if on_progress is not None else None
    )
    fetch_s = time.monotonic() - t0

    combined = pd.DataFrame(columns=signal_store.COLUMNS)
    hit_counts: dict[str, int] = {}
    new_today_frames: list[pd.DataFrame] = []
    for setup_name, scan_fn in _SCANS.items():
        if on_progress is not None:
            on_progress(f"Fetched {len(universe_ohlcv)}/{len(symbols)}. Scanning {setup_name}...")
        hits = scan_fn(universe_ohlcv)
        hit_counts[setup_name] = len(hits)
        combined = signal_store.merge_and_save(setup_name, hits)
        if not hits.empty:
            merged_setup_rows = combined[combined["setup"] == setup_name]
            first_time_today = set(merged_setup_rows.loc[merged_setup_rows["times_seen"] == 1, "symbol"])
            new_hits = hits[hits["symbol"].isin(first_time_today)]
            if not new_hits.empty:
                tagged = new_hits.copy()
                tagged.insert(0, "setup", setup_name)
                new_today_frames.append(tagged)

    new_today_hits = (
        pd.concat(new_today_frames, ignore_index=True) if new_today_frames else pd.DataFrame(columns=_HITS_COLUMNS)
    )

    total_s = time.monotonic() - t0
    _log.info(
        f"run_all: fetched {len(universe_ohlcv)}/{len(symbols)} symbols in {fetch_s:.1f}s, "
        f"hits={hit_counts}, new_today={len(new_today_hits)}, total_rows_today={len(combined)}, "
        f"total_time={total_s:.1f}s"
    )
    return combined, new_today_hits


if __name__ == "__main__":
    run_all()
