"""
Telegram bot configuration — same access-control model as the sibling
``PROJECT_TRADE_BOT`` (admin user id + optional env allowlist + a bot-managed
extra-ids file), same ``.env`` variable names.

- ``TELEGRAM_BOT_TOKEN`` — required to enable the bot at all.
- ``ADMIN_USER_ID`` — required; the one Telegram user id allowed to manage
  the allowlist (``/admin_add``, ``/admin_remove``, ``/admin_list``) and who
  always receives push notifications.
- ``ALLOWED_USER_IDS`` — optional, comma-separated. If this AND the
  bot-managed list are both empty, the bot is open to any Telegram user (same
  "open if nothing configured" behavior as the sibling project).

Unlike the sibling project, ``ADMIN_USER_ID`` has no hardcoded fallback here
— it must be set in ``.env``, since defaulting to someone else's personal
Telegram id would be wrong for a fresh project.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAX_UPLOAD_BYTES = 48 * 1024 * 1024


def _parse_allowed_ids(raw: str | None) -> set[int]:
    if not raw or not str(raw).strip():
        return set()
    out: set[int] = set()
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


@dataclass(frozen=True)
class TelegramConfig:
    telegram_token: str
    project_root: Path
    allowed_user_ids: set[int]
    admin_user_id: int
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    def is_user_allowed(self, user_id: int | None) -> bool:
        from .allowlist_store import read_extra_user_ids

        if user_id is None:
            return False
        uid = int(user_id)
        if uid == int(self.admin_user_id):
            return True
        env_ids = self.allowed_user_ids
        extra = read_extra_user_ids(self.project_root)
        if not env_ids and not extra:
            return True
        return uid in env_ids | extra

    def broadcast_user_ids(self) -> set[int]:
        """Every user id automatic push notifications go to: admin + the whole allowlist."""
        from .allowlist_store import read_extra_user_ids

        return {self.admin_user_id} | self.allowed_user_ids | read_extra_user_ids(self.project_root)


def telegram_configured() -> bool:
    """Cheap check used by run_scheduler.py to decide whether to enable the bot at all."""
    load_dotenv(_PROJECT_ROOT / ".env")
    return bool((os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip())


def load_telegram_config() -> TelegramConfig:
    load_dotenv(_PROJECT_ROOT / ".env")
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing. Copy .env.example to .env and set it.")

    admin_raw = (os.environ.get("ADMIN_USER_ID") or "").strip()
    if not admin_raw:
        raise RuntimeError("ADMIN_USER_ID missing. Set it in .env to your numeric Telegram user id.")
    try:
        admin_user_id = int(admin_raw)
    except ValueError:
        raise RuntimeError("ADMIN_USER_ID in .env must be a numeric Telegram user id.")
    if admin_user_id <= 0:
        raise RuntimeError("ADMIN_USER_ID in .env must be a positive integer.")

    allowed = _parse_allowed_ids(os.environ.get("ALLOWED_USER_IDS"))
    return TelegramConfig(
        telegram_token=token,
        project_root=_PROJECT_ROOT,
        allowed_user_ids=allowed,
        admin_user_id=admin_user_id,
    )
