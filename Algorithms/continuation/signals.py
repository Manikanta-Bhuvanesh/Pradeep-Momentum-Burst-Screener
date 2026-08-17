"""
Continuation ("2Lynch") entry detection — Trading_Webinar_Strategy_Summary.md §3.3.

Mechanizes the "3Q" framework using a fixed, vectorized lookback window
rather than an explicit leg/pullback search:

- A candidate "first leg" is the run-up from the lowest close in the
  ``LEG_LOOKBACK_DAYS`` window before the pullback, up to the highest high in
  the ``PULLBACK_MAX_DAYS`` window right before today (Q1: size + a
  majority-up-days persistence proxy).
- The pullback window itself must not have closed below 1/3 of the leg's
  gain given back, no single day in it may have dropped more than
  ``SINGLE_DAY_DRAWDOWN_MAX_PCT``, AND the peak must be strictly older than
  the most recent ``PULLBACK_MIN_DAYS`` days — i.e. price genuinely went
  quiet for a few days rather than just continuing to grind to new highs
  (Q2; see the bugfix note below).
- Today must break the pullback-window high, close near its own high, and
  NOT have been preceded by a day already up more than a token amount —
  i.e. not up 2 days running into the breakout (Q3).

**Bugfix (flagged by a user's friend, verified and confirmed real)**: the
original version computed ``peak_high`` and ``consolidation_low`` over the
*same* trailing window with no check on *where in that window* the peak
actually occurred. For a stock simply rising every single day with no real
pause, the window's low sits naturally close to its high (nothing was ever
given back) and "breakout" degenerated to "today's close clears yesterday's
high" — true on almost any decent up-day in a straight-line rally, not the
leg-then-pause-then-second-breakout shape the setup is supposed to detect.
The fix adds an explicit check that the peak is NOT within the most recent
``PULLBACK_MIN_DAYS`` days (default 2 — "1 day doesn't count as a real
pause" per the source), i.e. that a genuine multi-day quiet spell actually
happened before today's breakout.

The source material itself calls picking the *exact* leg number (2nd/3rd vs.
4th/5th) inherently visual/manual (§3.3, and the playbook's own Chartink
starting filter is explicitly "refine yourself"). This implementation
intentionally does not attempt leg-counting — it mechanizes the parts of the
3Q framework that ARE precisely quantified in the source, and accepts any
setup that clears the bar as a qualifying "2Lynch"-shaped continuation.
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

    pb = settings.PULLBACK_MAX_DAYS
    pb_min = settings.PULLBACK_MIN_DAYS
    leg_win = settings.LEG_LOOKBACK_DAYS

    peak_high = high.shift(1).rolling(pb, min_periods=pb).max()
    consolidation_low = close.shift(1).rolling(pb, min_periods=pb).min()
    leg_ref_low = close.shift(1 + pb).rolling(leg_win, min_periods=leg_win).min()

    # The peak must be OLDER than the most recent pb_min days — i.e. price has
    # genuinely gone quiet for at least pb_min days, not just kept climbing.
    recent_high = high.shift(1).rolling(pb_min, min_periods=pb_min).max()
    genuine_pause = recent_high < peak_high

    leg_gain_pct = (peak_high - leg_ref_low) / leg_ref_low * 100.0
    leg_size_ok = leg_gain_pct >= settings.FIRST_LEG_MIN_GAIN_PCT

    is_up_day = (close > close.shift(1)).astype(float)
    leg_up_day_fraction = is_up_day.shift(1 + pb).rolling(leg_win, min_periods=leg_win).mean()
    leg_persistent = leg_up_day_fraction >= settings.LEG_UP_DAY_FRACTION_MIN

    giveback_floor = peak_high - (peak_high - leg_ref_low) * settings.PULLBACK_GIVEBACK_FRACTION
    pullback_holds = consolidation_low >= giveback_floor

    daily_ret_pct = close.pct_change() * 100.0
    worst_pullback_day = daily_ret_pct.shift(1).rolling(pb, min_periods=pb).min()
    no_bad_pullback_day = worst_pullback_day >= -settings.SINGLE_DAY_DRAWDOWN_MAX_PCT

    breakout = close > peak_high
    day_range = (high - low).clip(lower=1e-9)
    close_near_high = (close - low) >= settings.CLOSE_NEAR_HIGH_FRACTION * day_range

    prior_day_ret_pct = (close.shift(1) / close.shift(2) - 1.0) * 100.0
    not_up_2_days_running = prior_day_ret_pct <= settings.PRIOR_DAY_MAX_UP_PCT

    avg_vol = volume.rolling(
        settings.AVG_VOLUME_WINDOW, min_periods=max(5, settings.AVG_VOLUME_WINDOW // 2)
    ).mean()
    liquid = avg_vol >= settings.MIN_AVG_VOLUME_SHARES

    trigger = (
        leg_size_ok
        & leg_persistent
        & pullback_holds
        & no_bad_pullback_day
        & genuine_pause
        & breakout
        & close_near_high
        & not_up_2_days_running
        & liquid
    )
    return trigger.fillna(False)
