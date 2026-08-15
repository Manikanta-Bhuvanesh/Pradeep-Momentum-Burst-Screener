"""
Quiet-mode logging: everything goes to ``output/scheduler.log``, nothing to
the console. This project is meant to run unattended on its own internal
schedule (see run_scheduler.py) — stdout must stay clean, so no module in
this project calls ``print()``. Check ``output/scheduler.log`` for a record
of every run, and ``output/live_signals.csv`` / ``output/archive/`` for
results.
"""
from __future__ import annotations

import logging
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = _PROJECT_ROOT / "output" / "scheduler.log"

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("live_screener")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False  # never bubble up to root's console handler
    _logger = logger
    return logger
