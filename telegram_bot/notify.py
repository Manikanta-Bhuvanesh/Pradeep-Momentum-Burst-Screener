"""Format and push this-run's screener hits to every authorized Telegram user."""
from __future__ import annotations

import html
from typing import TYPE_CHECKING

import pandas as pd

from common.logging_setup import get_logger

if TYPE_CHECKING:
    from telegram import Bot

_log = get_logger()

_MAX_CHARS = 3800  # margin under Telegram's 4096 hard limit


def format_hits_blocks(hits_df: pd.DataFrame, scan_time_label: str) -> list[str]:
    """
    One HTML message (or several, split at hit boundaries) listing every hit
    from a single scan run: stock name, setup name, note — the exact fields
    the user asked to see immediately after each run.
    """
    if hits_df is None or hits_df.empty:
        return []

    header = f"\U0001f4c8 <b>Live Screener</b> — {html.escape(scan_time_label)}\n\n"
    entries: list[str] = []
    for _, row in hits_df.iterrows():
        symbol = html.escape(str(row.get("symbol", "")))
        setup = html.escape(str(row.get("setup", "")))
        note = html.escape(str(row.get("note", "")))
        entries.append(f"<b>{symbol}</b> — {setup}\n{note}")

    blocks: list[str] = []
    current = header
    for entry in entries:
        addition = (entry + "\n\n")
        if len(current) + len(addition) > _MAX_CHARS and current != header:
            blocks.append(current.rstrip())
            current = ""
        current += addition
    if current.strip():
        blocks.append(current.rstrip())
    return blocks


async def push_hits(bot: "Bot", chat_ids: set[int], hits_df: pd.DataFrame, scan_time_label: str) -> None:
    blocks = format_hits_blocks(hits_df, scan_time_label)
    if not blocks:
        return
    for chat_id in chat_ids:
        for block in blocks:
            try:
                await bot.send_message(chat_id=chat_id, text=block, parse_mode="HTML")
            except Exception as exc:  # noqa: BLE001 — one bad chat id must not stop the others
                _log.warning(f"push_hits: failed to message chat_id={chat_id}: {exc}")
