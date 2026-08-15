"""
Anticipation entry detection — Trading_Webinar_Strategy_Summary.md §9, Playbook §4.

1. Stock already has an established uptrend over ``TREND_LOOKBACK_DAYS``
   (a real first leg, not flat/down).
2. Today is a volatility-compression / "quiet" day: |daily change| within
   ``TIGHT_DAY_MAX_ABS_PCT``.
3. Higher-priced/liquid preference: price and liquidity floors.
4. Bull-market regime confirmed (injected via ``bull_regime_dates``, computed
   once across the Nifty 500 universe by ``common.breadth`` — cannot be
   derived from a single symbol's OHLCV alone, same reasoning as Bottom
   Bounce's oversold gate).

The "skip pending buyout/merger targets" rule is explicitly a news-based
judgment call in the source material — not something OHLCV can detect, so no
code models it; flagged here for anyone reviewing the live output by hand.
"""
from __future__ import annotations

import pandas as pd

from . import settings


def raw_setup_conditions(ohlcv: pd.DataFrame) -> pd.Series:
    if ohlcv is None or len(ohlcv) < settings.MIN_OHLCV_ROWS:
        return pd.Series(False, index=ohlcv.index if ohlcv is not None else pd.RangeIndex(0))

    close = ohlcv["close"].astype(float)
    volume = ohlcv["volume"].astype(float).clip(lower=0.0)

    trend_ref = close.shift(settings.TREND_LOOKBACK_DAYS)
    trend_gain_pct = (close.shift(1) / trend_ref - 1.0) * 100.0
    established_uptrend = trend_gain_pct >= settings.TREND_MIN_GAIN_PCT

    daily_change_pct = (close / close.shift(1) - 1.0) * 100.0
    is_quiet_day = daily_change_pct.abs() <= settings.TIGHT_DAY_MAX_ABS_PCT

    price_ok = close >= settings.MIN_PRICE_RUPEES

    avg_vol = volume.rolling(
        settings.AVG_VOLUME_WINDOW, min_periods=max(5, settings.AVG_VOLUME_WINDOW // 2)
    ).mean()
    liquid = avg_vol >= settings.MIN_AVG_VOLUME_SHARES

    return (established_uptrend & is_quiet_day & price_ok & liquid).fillna(False)
