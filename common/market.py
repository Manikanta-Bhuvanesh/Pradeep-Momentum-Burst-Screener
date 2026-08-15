"""
Nifty 500 / Nifty 200 universe loading.

Nifty 500 is the broad scan universe (Consolidation Breakout, Continuation,
Anticipation). Nifty 200 is the extra liquidity/quality gate used specifically
for Bottom Bounce (the webinar restricts that setup to index-quality names —
see Trading_Webinar_Strategy_Summary.md §3.1).

Source CSVs are NSE's own published index-constituent lists
(niftyindices.com/IndexConstituent/ind_nifty{500,200}list.csv), saved as
input/NIFTY500.csv and input/NIFTY200.csv. Re-download periodically — index
membership changes at each periodic NSE index reshuffle.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
NIFTY500_CSV: Path = _PROJECT_ROOT / "input" / "NIFTY500.csv"
NIFTY200_CSV: Path = _PROJECT_ROOT / "input" / "NIFTY200.csv"


def _load_symbols(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    df["symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    df = df.rename(columns={"Company Name": "company_name", "Industry": "industry"})
    return df[["symbol", "company_name", "industry"]].drop_duplicates(subset="symbol")


def load_nifty500() -> pd.DataFrame:
    return _load_symbols(NIFTY500_CSV)


def load_nifty200() -> pd.DataFrame:
    return _load_symbols(NIFTY200_CSV)


def nifty500_symbols() -> list[str]:
    return load_nifty500()["symbol"].tolist()


def nifty200_symbols() -> list[str]:
    return load_nifty200()["symbol"].tolist()


def nifty200_symbol_set() -> set[str]:
    return set(nifty200_symbols())


def universe_with_quality_flag() -> pd.DataFrame:
    """Nifty 500 list with an ``is_nifty200`` column marking the quality/liquid subset."""
    n500 = load_nifty500()
    n200 = nifty200_symbol_set()
    n500["is_nifty200"] = n500["symbol"].isin(n200)
    return n500
