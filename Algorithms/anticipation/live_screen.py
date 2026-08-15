"""
Anticipation live/forward daily screen (Nifty 500).

Best run late in the session (~2:50-3:30 PM IST) so the "today" bar reflects
the live, still-forming session — see runner.run_live_screen's output note.

Usage::

    python -m Algorithms.anticipation.live_screen
"""
from __future__ import annotations

from .runner import run_live_screen

if __name__ == "__main__":
    run_live_screen()
