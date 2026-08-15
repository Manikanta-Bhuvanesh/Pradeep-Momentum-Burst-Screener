"""
Optional SMTP email when a live-signals CSV contains one or more rows.

Credentials are read from ``.env`` at the project root (copy from ``.env.example``).
Use a Gmail *App Password* (2FA required), not your normal Gmail password.

Enable mail when live screen finds signals (non-empty CSV):

- Set ``EMAIL_ON_LIVE_SIGNALS = True`` in ``Algorithms/.../settings.py`` **and**
- Fill in ``.env`` at the project root:

  ``TRADE_PILOT_SMTP_HOST`` — default ``smtp.gmail.com``  
  ``TRADE_PILOT_SMTP_PORT`` — default ``587``  
  ``TRADE_PILOT_SMTP_USER`` — Gmail address used to authenticate  
  ``TRADE_PILOT_SMTP_PASSWORD`` — app password  
  ``TRADE_PILOT_EMAIL_TO`` — comma-separated recipient addresses  
  ``TRADE_PILOT_EMAIL_FROM`` — optional; defaults to ``TRADE_PILOT_SMTP_USER``

If any required variable is missing, the function logs a short message to stderr and returns.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

from common.logging_setup import get_logger

_log = get_logger()
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _PROJECT_ROOT / ".env"
_env_loaded = False


def _ensure_env_loaded() -> None:
    global _env_loaded
    if _env_loaded:
        return
    if _ENV_FILE.is_file():
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE)
    _env_loaded = True


def mail_live_signals_csv_if_nonempty(
    *,
    csv_path: Path,
    strategy_label: str,
    subject_prefix: str = "Trade Pilot",
) -> None:
    """
    If ``csv_path`` exists, is readable, and has at least one data row, send it as an attachment.

    Credentials come from ``.env`` at the project root (see module docstring).
    """
    if not csv_path.is_file():
        return
    try:
        df = pd.read_csv(csv_path)
    except (OSError, pd.errors.EmptyDataError, ValueError) as e:
        _log.warning(f"live_signal_email: skip mail, could not read CSV: {e}")
        return
    if df.empty:
        return

    _ensure_env_loaded()

    host = os.environ.get("TRADE_PILOT_SMTP_HOST", "smtp.gmail.com").strip()
    port_s = os.environ.get("TRADE_PILOT_SMTP_PORT", "587").strip()
    user = os.environ.get("TRADE_PILOT_SMTP_USER", "").strip()
    password = os.environ.get("TRADE_PILOT_SMTP_PASSWORD", "").strip()
    to_raw = os.environ.get("TRADE_PILOT_EMAIL_TO", "").strip()
    mail_from = os.environ.get("TRADE_PILOT_EMAIL_FROM", user).strip()

    try:
        port = int(port_s)
    except ValueError:
        _log.warning("live_signal_email: TRADE_PILOT_SMTP_PORT invalid")
        return

    if not user or not password or not to_raw:
        _log.warning(
            "live_signal_email: missing TRADE_PILOT_SMTP_USER, TRADE_PILOT_SMTP_PASSWORD, "
            "or TRADE_PILOT_EMAIL_TO in .env — not sending mail."
        )
        return

    receivers = [x.strip() for x in to_raw.split(",") if x.strip()]
    if not receivers:
        _log.warning("live_signal_email: TRADE_PILOT_EMAIL_TO has no addresses")
        return

    n = len(df)
    subject = f"{subject_prefix}: {strategy_label} — {n} signal(s)"
    body = (
        f"The live screen for **{strategy_label}** found **{n}** row(s) with a buy/sell signal "
        f"on the latest bar.\n\n"
        f"CSV attached: {csv_path.name}\n"
    )

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(receivers)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    data = csv_path.read_bytes()
    part = MIMEApplication(data, Name=csv_path.name)
    part.add_header("Content-Disposition", "attachment", filename=csv_path.name)
    msg.attach(part)

    try:
        with smtplib.SMTP(host, port, timeout=60) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
    except OSError as e:
        _log.warning(f"live_signal_email: SMTP failed: {e}")
