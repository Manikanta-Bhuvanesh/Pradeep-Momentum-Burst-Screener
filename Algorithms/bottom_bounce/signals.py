"""
Bottom Bounce entry detection.

Mechanical translation of Trading_Webinar_Strategy_Summary.md §3.1:
1. Stock recently touched a new N-day low (``NEW_LOW_LOOKBACK_DAYS``).
2. Today is a range-expansion day (today's high-low range exceeds every one
   of the prior ``RANGE_EXPANSION_LOOKBACK_DAYS`` days' ranges).
3. Today's close takes out at least the prior ``MIN_HIGH_BREAKOUT_DAYS``
   days' high.
4. Today closes up (the reversal itself).
5. Liquidity floor met (volume is explicitly NOT required to be elevated —
   the source is clear most volume happens in the prior sell-off, not the
   bounce day).
6. The market as a whole is oversold on this date (injected via
   ``oversold_dates`` — computed once across the whole Nifty 200 universe by
   ``common.breadth``, not derivable from a single symbol's OHLCV alone).

The "don't try to predict the bottom with candlestick patterns" rule needs no
code — it is a negative instruction (don't build a hammer-pattern detector).
"""
from __future__ import annotations

import pandas as pd

from . import settings


def _hold_series(index: pd.Index) -> pd.Series:
    return pd.Series(False, index=index)


def raw_setup_conditions(ohlcv: pd.DataFrame) -> pd.Series:
    """Per-symbol conditions only (new low + range expansion + breakout + liquidity), no breadth gate."""
    if ohlcv is None or len(ohlcv) < settings.MIN_OHLCV_ROWS:
        return _hold_series(ohlcv.index if ohlcv is not None else pd.RangeIndex(0))

    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    close = ohlcv["close"].astype(float)
    volume = ohlcv["volume"].astype(float).clip(lower=0.0)

    rolling_low_prior = low.shift(1).rolling(
        settings.NEW_LOW_LOOKBACK_DAYS, min_periods=max(20, settings.NEW_LOW_LOOKBACK_DAYS // 2)
    ).min()
    tol = 1.0 + settings.NEW_LOW_TOLERANCE_PCT / 100.0
    touched_new_low = (low <= rolling_low_prior * tol) | (low.shift(1) <= rolling_low_prior.shift(1) * tol)

    day_range = high - low
    prior_max_range = day_range.shift(1).rolling(
        settings.RANGE_EXPANSION_LOOKBACK_DAYS, min_periods=settings.RANGE_EXPANSION_LOOKBACK_DAYS
    ).max()
    is_range_expansion = day_range > prior_max_range

    prior_high_n = high.shift(1).rolling(
        settings.MIN_HIGH_BREAKOUT_DAYS, min_periods=settings.MIN_HIGH_BREAKOUT_DAYS
    ).max()
    takes_out_high = close > prior_high_n

    is_up_day = close > close.shift(1)

    avg_vol = volume.rolling(settings.AVG_VOLUME_WINDOW, min_periods=max(5, settings.AVG_VOLUME_WINDOW // 2)).mean()
    liquid = avg_vol >= settings.MIN_AVG_VOLUME_SHARES

    return (touched_new_low & is_range_expansion & takes_out_high & is_up_day & liquid).fillna(False)
