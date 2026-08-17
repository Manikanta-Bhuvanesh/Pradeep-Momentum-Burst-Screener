"""
Continuation ("2Lynch") — Trading_Webinar_Strategy_Summary.md §3.3, Trading_Playbook §3.

The course's bread-and-butter setup. Universe: Nifty 500.
Live screen only — no backtest, no exit management.
"""
from __future__ import annotations

import os

SETUP_NAME: str = "continuation"  # key used in the shared output/live_signals.csv

FETCH_PERIOD: str = "1y"
FETCH_INTERVAL: str = "1d"
FETCH_BATCH_SIZE: int = 8
FETCH_YF_THREADS: bool = True
MIN_OHLCV_ROWS: int = 120

# ── The "3Q" framework, mechanized (Trading_Webinar_Strategy_Summary.md §3.3) ─
# Q1 — quality of the first leg: a genuine run-up, not one isolated gap.
LEG_LOOKBACK_DAYS: int = 10  # window searched for the first-leg run-up before the consolidation
FIRST_LEG_MIN_GAIN_PCT: float = 8.0  # "look for a first leg that was itself ~20%+" to find a 20%+ next
                                       # leg; 8% is used as the qualifying floor (course's own 8-20% base range)
LEG_UP_DAY_FRACTION_MIN: float = 0.5  # "persistent, linear buying" proxy: majority of leg days must be up days

# Q2 — quality of the consolidation/pullback.
PULLBACK_MAX_DAYS: int = 7  # "ideal 3-7 days" (2 OK in a strong market, beyond ~10 needs high volume)
PULLBACK_MIN_DAYS: int = 2  # "1 day doesn't count as a real pause" — require a genuine multi-day quiet spell
PULLBACK_GIVEBACK_FRACTION: float = 1.0 / 3.0  # must NOT give back more than 1/3 of the first leg's gain
SINGLE_DAY_DRAWDOWN_MAX_PCT: float = 4.0  # "at most one single day with a <=4% breakdown is tolerable"

# Q3 — quality of the breakout day.
CLOSE_NEAR_HIGH_FRACTION: float = 0.7  # closes near the high
PRIOR_DAY_MAX_UP_PCT: float = 0.5  # must NOT already be up 2 days in a row heading into the breakout

AVG_VOLUME_WINDOW: int = 20
MIN_AVG_VOLUME_SHARES: float = 50_000.0

PROCESS_POOL_MAX_WORKERS: int | None = None
MAX_SYMBOLS: int | None = None


def process_pool_workers() -> int:
    if PROCESS_POOL_MAX_WORKERS is not None and PROCESS_POOL_MAX_WORKERS > 0:
        return int(PROCESS_POOL_MAX_WORKERS)
    return min(32, max(1, (os.cpu_count() or 4)))
