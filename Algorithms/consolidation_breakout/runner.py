from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]


def _ensure_root_on_path() -> None:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


_ensure_root_on_path()

import pandas as pd
from tqdm.auto import tqdm

from common import market, signal_store
from common.logging_setup import get_logger
from common.universe_data import fetch_universe_ohlcv as _fetch_universe_ohlcv

from . import settings
from .signals import raw_setup_conditions

_log = get_logger()


def fetch_universe_ohlcv(symbols: list[str]) -> dict[str, pd.DataFrame]:
    return _fetch_universe_ohlcv(
        symbols,
        period=settings.FETCH_PERIOD,
        interval=settings.FETCH_INTERVAL,
        batch_size=settings.FETCH_BATCH_SIZE,
        threads=settings.FETCH_YF_THREADS,
        min_rows=settings.MIN_OHLCV_ROWS,
    )


def scan(universe_ohlcv: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pure scan over an already-fetched universe — no fetching here (see run_all_live_screens.py)."""
    rows: list[dict[str, Any]] = []
    for sym, ohlcv in tqdm(universe_ohlcv.items(), desc="Consolidation Breakout scan", unit="sym"):
        setup = raw_setup_conditions(ohlcv)
        if len(setup) == 0 or not bool(setup.iloc[-1]):
            continue
        rows.append(
            {
                "symbol": sym,
                "trigger_date": pd.Timestamp(ohlcv["date"].iloc[-1]).normalize().isoformat(),
                "trigger_close": float(ohlcv["close"].iloc[-1]),
                "note": "Enter next session's open (or as early as possible intraday).",
            }
        )
    return pd.DataFrame(rows)


def run_live_screen() -> pd.DataFrame:
    """Standalone entry point: fetch Nifty 500 alone, scan, merge into the shared CSV."""
    n500 = market.load_nifty500()
    symbols = n500["symbol"].tolist()
    if settings.MAX_SYMBOLS is not None:
        symbols = symbols[: settings.MAX_SYMBOLS]

    universe_ohlcv = fetch_universe_ohlcv(symbols)
    hits = scan(universe_ohlcv)
    updated = signal_store.merge_and_save(settings.SETUP_NAME, hits)
    _log.info(f"[{settings.SETUP_NAME}] {len(hits)} hit(s) this run ({len(universe_ohlcv)}/{len(symbols)} fetched)")
    return updated
