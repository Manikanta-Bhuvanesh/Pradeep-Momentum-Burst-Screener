"""
Consolidation Breakout entry detection — Trading_Webinar_Strategy_Summary.md §3.2.

1. A long sideways base: the prior ``BASE_LOOKBACK_DAYS`` trading days stayed
   within a ``BASE_MAX_RANGE_PCT`` high/low band.
2. Breakout day: close clears the base's high.
3. Volume is the defining ingredient here (unlike Bottom Bounce) — today's
   volume must be at least ``RELATIVE_VOLUME_MULT`` times the trailing
   average ("a visually obvious skyscraper bar").
4. Close near the day's high (genuine demand, not a fade).
5. Liquidity floor so the volume-surge ratio is meaningful.
"""
from __future__ import annotations

import pandas as pd

from . import settings


def raw_setup_conditions(ohlcv: pd.DataFrame) -> pd.Series:
    if ohlcv is None or len(ohlcv) < settings.MIN_OHLCV_ROWS:
        return pd.Series(False, index=ohlcv.index if ohlcv is not None else pd.RangeIndex(0))

    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    close = ohlcv["close"].astype(float)
    volume = ohlcv["volume"].astype(float).clip(lower=0.0)

    base_high = high.shift(1).rolling(settings.BASE_LOOKBACK_DAYS, min_periods=settings.BASE_LOOKBACK_DAYS).max()
    base_low = low.shift(1).rolling(settings.BASE_LOOKBACK_DAYS, min_periods=settings.BASE_LOOKBACK_DAYS).min()
    base_range_pct = (base_high / base_low - 1.0) * 100.0
    is_sideways_base = base_range_pct <= settings.BASE_MAX_RANGE_PCT

    breaks_out = close > base_high

    vol_avg = volume.shift(1).rolling(
        settings.VOLUME_AVG_WINDOW, min_periods=max(5, settings.VOLUME_AVG_WINDOW // 2)
    ).mean()
    volume_surge = volume >= settings.RELATIVE_VOLUME_MULT * vol_avg

    day_range = (high - low).clip(lower=1e-9)
    close_near_high = (close - low) >= settings.CLOSE_NEAR_HIGH_FRACTION * day_range

    liquid_avg = volume.rolling(
        settings.AVG_VOLUME_WINDOW, min_periods=max(5, settings.AVG_VOLUME_WINDOW // 2)
    ).mean()
    liquid = liquid_avg >= settings.MIN_AVG_VOLUME_SHARES

    return (is_sideways_base & breaks_out & volume_surge & close_near_high & liquid).fillna(False)
