"""
India substitute for the course's T2108 breadth indicator, computed straight
from the Nifty 200 constituents' own OHLCV (no external breadth feed needed).

T2108 = % of S&P 500 stocks trading above their 40-day moving average; the
course's single most important Bottom Bounce precondition is T2108 < 20 (see
Trading_Webinar_Strategy_Summary.md §3.1 and §13). We reproduce that exact
definition over the Nifty 200 (the "quality" index used for Bottom Bounce)
instead of the S&P 500.

Per the user's explicit instruction, the oversold gate does not rely on
``pct_above_ma`` alone — it also requires a confirming advance/decline
signal (a rolling share of the universe actively declining), matching the
webinar's own qualitative description: "if declines massively outnumber
advances for several days running" (Trading_Playbook §1.1 / §10 T2108 note).
A crude "index down X% from a high" proxy was tried in an earlier, since-
scrapped build and flagged there as possibly too crude a T2108 substitute —
this direct breadth computation is a deliberate improvement over that.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BreadthConfig:
    ma_window: int = 40  # T2108's own definition: % above the 40-day MA
    pct_above_ma_oversold: float = 20.0  # course's exact T2108 < 20 threshold
    decline_confirm_window: int = 3  # "several days running"
    pct_declining_confirm: float = 55.0  # rolling avg % of universe declining
    require_decline_confirmation: bool = True


def compute_breadth(ohlcv_by_symbol: dict[str, pd.DataFrame], cfg: BreadthConfig = BreadthConfig()) -> pd.DataFrame:
    """
    Build a daily breadth table from a universe of per-symbol OHLCV frames
    (each with ``date``/``close`` columns, as returned by
    ``data_fetcher.prepare_ohlcv_df``).

    Returns a DataFrame indexed by date (ascending) with:

    - ``pct_above_ma``   — % of universe stocks with close > their own
                            ``ma_window``-day SMA that day (T2108 equivalent).
    - ``advancers`` / ``decliners`` / ``unchanged`` — daily counts.
    - ``pct_declining``  — decliners / (advancers+decliners+unchanged) * 100.
    - ``pct_declining_roll`` — rolling mean of ``pct_declining`` over
                            ``decline_confirm_window`` sessions.
    """
    rows: list[pd.DataFrame] = []
    for sym, raw in ohlcv_by_symbol.items():
        if raw is None or raw.empty or "close" not in raw.columns:
            continue
        d = raw[["date", "close"]].copy()
        d["close"] = pd.to_numeric(d["close"], errors="coerce")
        d.dropna(subset=["date", "close"], inplace=True)
        if len(d) < cfg.ma_window + 1:
            continue
        d.sort_values("date", inplace=True)
        d["sma"] = d["close"].rolling(cfg.ma_window, min_periods=cfg.ma_window).mean()
        d["prev_close"] = d["close"].shift(1)
        d["is_above_ma"] = d["close"] > d["sma"]
        d["is_advancer"] = d["close"] > d["prev_close"]
        d["is_decliner"] = d["close"] < d["prev_close"]
        d["is_unchanged"] = d["close"] == d["prev_close"]
        d["symbol"] = sym
        rows.append(d[["date", "sma", "is_above_ma", "is_advancer", "is_decliner", "is_unchanged"]])

    if not rows:
        return pd.DataFrame(
            columns=["pct_above_ma", "advancers", "decliners", "unchanged", "pct_declining", "pct_declining_roll"]
        )

    long_df = pd.concat(rows, ignore_index=True)
    long_df["date"] = pd.to_datetime(long_df["date"])

    ma_ready = long_df.dropna(subset=["sma"])
    pct_above_ma = ma_ready.groupby("date")["is_above_ma"].mean().mul(100.0).rename("pct_above_ma")

    grp = long_df.groupby("date")
    advancers = grp["is_advancer"].sum().rename("advancers")
    decliners = grp["is_decliner"].sum().rename("decliners")
    unchanged = grp["is_unchanged"].sum().rename("unchanged")

    breadth = pd.concat([pct_above_ma, advancers, decliners, unchanged], axis=1).sort_index()
    total = (breadth["advancers"] + breadth["decliners"] + breadth["unchanged"]).astype(float)
    total = total.where(total > 0, other=float("nan"))
    breadth["pct_declining"] = (breadth["decliners"].astype(float) / total * 100.0)
    breadth["pct_declining_roll"] = (
        breadth["pct_declining"].rolling(cfg.decline_confirm_window, min_periods=1).mean()
    )
    breadth.index.name = "date"
    return breadth


def oversold_mask(breadth: pd.DataFrame, cfg: BreadthConfig = BreadthConfig()) -> pd.Series:
    """
    Boolean series (indexed like ``breadth``) marking dates the market qualifies
    as "oversold" for Bottom Bounce: T2108-equivalent < threshold, AND (unless
    disabled) a confirming rolling share of the universe actively declining.
    """
    if breadth.empty:
        return pd.Series(dtype=bool)
    below_ma = breadth["pct_above_ma"] < cfg.pct_above_ma_oversold
    if not cfg.require_decline_confirmation:
        return below_ma.fillna(False)
    declining_confirmed = breadth["pct_declining_roll"] >= cfg.pct_declining_confirm
    return (below_ma & declining_confirmed).fillna(False)
