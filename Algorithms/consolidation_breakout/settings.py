"""
Consolidation Breakout — Trading_Webinar_Strategy_Summary.md §3.2, Trading_Playbook §2.

Universe: Nifty 500 (the huge volume surge itself is the quality filter, per
the playbook's own India note — no extra liquidity-index restriction needed).
Live screen only — no backtest, no exit management.
"""
from __future__ import annotations

import os

SETUP_NAME: str = "consolidation_breakout"  # key used in the shared output/live_signals.csv

FETCH_PERIOD: str = "1y"
FETCH_INTERVAL: str = "1d"
FETCH_BATCH_SIZE: int = 8
FETCH_YF_THREADS: bool = True
MIN_OHLCV_ROWS: int = 120

# ── Entry thresholds (Trading_Webinar_Strategy_Summary.md §3.2) ─────────────
BASE_LOOKBACK_DAYS: int = 20  # minimum ~1 month sideways base (course allows up to a year+)
BASE_MAX_RANGE_PCT: float = 25.0  # base's high/low range must stay within this % to count as "sideways"
VOLUME_AVG_WINDOW: int = 20
RELATIVE_VOLUME_MULT: float = 3.0  # "3x to 10x average" — 3x is the qualifying floor
CLOSE_NEAR_HIGH_FRACTION: float = 0.7  # close must be in the top 30% of the day's range
AVG_VOLUME_WINDOW: int = 20
MIN_AVG_VOLUME_SHARES: float = 50_000.0  # base liquidity floor so the volume-surge ratio is meaningful

PROCESS_POOL_MAX_WORKERS: int | None = None
MAX_SYMBOLS: int | None = None


def process_pool_workers() -> int:
    if PROCESS_POOL_MAX_WORKERS is not None and PROCESS_POOL_MAX_WORKERS > 0:
        return int(PROCESS_POOL_MAX_WORKERS)
    return min(32, max(1, (os.cpu_count() or 4)))
