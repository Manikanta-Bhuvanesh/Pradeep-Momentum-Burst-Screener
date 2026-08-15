"""
Bottom Bounce — Trading_Webinar_Strategy_Summary.md §3.1, Trading_Playbook §1.

Universe: Nifty 500 — the source's original "quality index only" restriction
(Nifty 200) was dropped per explicit user request, so this setup can share
one fetch/scan pass with the other three instead of a separate Nifty-200-only
fetch. The T2108-equivalent breadth gate below still runs, just over the
wider Nifty 500 universe now. Live screen only — no backtest, no exit
management.
"""
from __future__ import annotations

import os

from common.breadth import BreadthConfig

SETUP_NAME: str = "bottom_bounce"  # key used in the shared output/live_signals.csv

FETCH_PERIOD: str = "1y"  # only recent history is needed for a live entry check
FETCH_INTERVAL: str = "1d"
FETCH_BATCH_SIZE: int = 8
FETCH_YF_THREADS: bool = True
MIN_OHLCV_ROWS: int = 120

# ── Entry thresholds (Trading_Webinar_Strategy_Summary.md §3.1) ─────────────
NEW_LOW_LOOKBACK_DAYS: int = 60  # ~3 months; course mentions 1/3/6/12mo, this is the primary window
NEW_LOW_TOLERANCE_PCT: float = 3.0  # "at/near" the rolling low, not required to be the exact tick low
RANGE_EXPANSION_LOOKBACK_DAYS: int = 5  # today's range must exceed the max of the prior N days' ranges
MIN_HIGH_BREAKOUT_DAYS: int = 3  # "takes out at least a 3-day high" (best examples: 5-6 days)
AVG_VOLUME_WINDOW: int = 20
MIN_AVG_VOLUME_SHARES: float = 100_000.0  # liquidity floor; volume surge itself is NOT required for BB

# ── Market-breadth oversold gate (T2108 equivalent: % of the universe above ─
# its own 40-day MA, confirmed by advance/decline breadth — see common/breadth.py)
BREADTH_CONFIG = BreadthConfig(
    ma_window=40,
    pct_above_ma_oversold=20.0,
    decline_confirm_window=3,
    pct_declining_confirm=55.0,
    require_decline_confirmation=True,
)

PROCESS_POOL_MAX_WORKERS: int | None = None
MAX_SYMBOLS: int | None = None  # cap the scan universe (e.g. for a quick test run)


def process_pool_workers() -> int:
    if PROCESS_POOL_MAX_WORKERS is not None and PROCESS_POOL_MAX_WORKERS > 0:
        return int(PROCESS_POOL_MAX_WORKERS)
    return min(32, max(1, (os.cpu_count() or 4)))
