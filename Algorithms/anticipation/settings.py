"""
Anticipation — Trading_Webinar_Strategy_Summary.md §9, Trading_Playbook §4.

Higher-skill, explicitly not-for-beginners timing variant on Continuation:
enter before the breakout confirms, on a volatility-compression ("quiet")
day. Universe: Nifty 500. Live screen only — no backtest, no exit management
(the source's real technique manages this by hand/discretion, see README).
"""
from __future__ import annotations

import os

from common.breadth import BreadthConfig

SETUP_NAME: str = "anticipation"  # key used in the shared output/live_signals.csv

FETCH_PERIOD: str = "1y"
FETCH_INTERVAL: str = "1d"
FETCH_BATCH_SIZE: int = 8
FETCH_YF_THREADS: bool = True
MIN_OHLCV_ROWS: int = 120

# ── Entry thresholds (Trading_Webinar_Strategy_Summary.md §9, Playbook §4) ──
TREND_LOOKBACK_DAYS: int = 63  # "the last ~1 month/quarter" established first leg
TREND_MIN_GAIN_PCT: float = 5.0  # must already be a real uptrend, not flat/down
TIGHT_DAY_MAX_ABS_PCT: float = 0.4  # "±0.4% for the day" volatility-compression trigger
MIN_PRICE_RUPEES: float = 800.0  # playbook's translated "under $10 destroys the edge" cutoff
AVG_VOLUME_WINDOW: int = 20
MIN_AVG_VOLUME_SHARES: float = 100_000.0  # source's high-price variant used a liquidity floor too

# "Only used in a bull market" — a bull-regime confirmation gate, mirroring the
# T2108-style breadth calc used for Bottom Bounce but pointed the OTHER way
# (require most of the market above its MA, not oversold). Computed over
# Nifty 500 since Anticipation itself scans Nifty 500.
BULL_REGIME_BREADTH_CONFIG = BreadthConfig(ma_window=50)
BULL_REGIME_MIN_PCT_ABOVE_MA: float = 50.0

PROCESS_POOL_MAX_WORKERS: int | None = None
MAX_SYMBOLS: int | None = None


def process_pool_workers() -> int:
    if PROCESS_POOL_MAX_WORKERS is not None and PROCESS_POOL_MAX_WORKERS > 0:
        return int(PROCESS_POOL_MAX_WORKERS)
    return min(32, max(1, (os.cpu_count() or 4)))
