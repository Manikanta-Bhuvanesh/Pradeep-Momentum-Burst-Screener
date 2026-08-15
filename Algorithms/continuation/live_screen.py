"""
Continuation ("2Lynch") live/forward daily screen (Nifty 500).

Usage::

    python -m Algorithms.continuation.live_screen
"""
from __future__ import annotations

from .runner import run_live_screen

if __name__ == "__main__":
    run_live_screen()
