"""
Shared OHLCV fetch helper.

All 4 setups now scan the same Nifty 500 universe (see market.py / README —
Bottom Bounce's Nifty 200 "quality" restriction was dropped per explicit
user request in favor of one shared fetch). ``run_all_live_screens.py``
fetches once and passes the same ``{symbol: ohlcv}`` dict into every setup's
``scan()``, instead of each setup re-fetching independently.

Fetch progress is shown in the terminal (tqdm, via ``show_progress=True``)
and can also be mirrored elsewhere (e.g. a Telegram progress message) via
``on_progress`` — a plain ``(completed, total)`` callback, not tied to tqdm.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from data_fetcher import fetch_indian_equities, prepare_ohlcv_df

DEFAULT_FETCH_PERIOD = "1y"
DEFAULT_FETCH_INTERVAL = "1d"
DEFAULT_FETCH_BATCH_SIZE = 8
DEFAULT_MIN_OHLCV_ROWS = 120


def fetch_universe_ohlcv(
    symbols: list[str],
    *,
    period: str = DEFAULT_FETCH_PERIOD,
    interval: str = DEFAULT_FETCH_INTERVAL,
    batch_size: int = DEFAULT_FETCH_BATCH_SIZE,
    threads: bool = True,
    min_rows: int = DEFAULT_MIN_OHLCV_ROWS,
    show_progress: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, pd.DataFrame]:
    batch = fetch_indian_equities(
        symbols,
        period=period,
        interval=interval,
        batch_size=batch_size,
        show_progress=show_progress,
        threads=threads,
        timeout=60.0,
        on_progress=on_progress,
    )
    out: dict[str, pd.DataFrame] = {}
    for sym, raw in batch.data.items():
        ohlcv = prepare_ohlcv_df(raw)
        if len(ohlcv) >= min_rows:
            out[sym] = ohlcv
    return out
