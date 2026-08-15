"""
Telegram bot + the scan loop, combined into one asyncio process.

Design note (deviation from the plain scheduler's original single-day,
auto-exit behavior): once Telegram is enabled, this runs INDEFINITELY —
the bot keeps listening for /next_schedule and /today_signals at any time
(including outside market hours, evenings, weekends), and the scan loop
sleeps through nights/weekends and resumes itself the next trading day, all
in one process. Without Telegram configured, run_scheduler.py falls back to
the original single-day loop that exits after the 3:15 PM run — see that
module for the plain path.

Commands:

- /start, /help — usage
- /next_schedule — when the next scan is due
- /today_signals — today's output/live_signals.csv so far, as a file
- /run_now — trigger a scan immediately, outside the 15-min schedule
- /admin_add, /admin_remove, /admin_list — allowlist management (admin only)

Automatic push: after every scan (scheduled OR /run_now) that finds at
least one NEW-for-today hit, every authorized user (admin + allowlist) gets
a message listing symbol, setup name, and note. A (setup, symbol) pair
already pushed once today is not pushed again even if it keeps matching on
later runs — see run_all_live_screens.py's ``new_today_hits`` semantics.
See common/schedule_window.py + run_all_live_screens.py. A shared lock
(bot_data["scan_lock"]) ensures a /run_now request and the scheduled loop
never run a scan at the same time — signal_store.merge_and_save does a
read-modify-write on one CSV file with no file locking of its own, so two
concurrent scans could race and lose an update.

Progress: while a scan runs (scheduled or /run_now), every authorized user
gets one message that's edited in place with fetch/scan progress (throttled
to at most one edit every ~2s, since ~500 fetch-progress callbacks in a
~50s run would otherwise hit Telegram's edit rate limits) — mirrors the
same tqdm-driven progress the terminal shows during a run.
"""
from __future__ import annotations

import asyncio
import functools
import html
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
from telegram import InputFile, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from common import signal_store
from common.logging_setup import get_logger
from common.schedule_window import (
    WINDOW_END,
    WINDOW_START,
    is_weekend,
    next_scheduled_run,
    now_ist,
    today_at,
)
from run_all_live_screens import run_all

from .allowlist_store import read_extra_user_ids, write_extra_user_ids
from .config import TelegramConfig
from .notify import push_hits

_log = get_logger()

SLOW_RUN_WARNING_MINUTES = 15
PROGRESS_EDIT_THROTTLE_S = 2.0


def _cfg(context: ContextTypes.DEFAULT_TYPE) -> TelegramConfig:
    return context.application.bot_data["config"]


def _is_admin(cfg: TelegramConfig, user_id: int | None) -> bool:
    return user_id is not None and int(user_id) == int(cfg.admin_user_id)


async def _ensure_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    cfg = _cfg(context)
    uid = update.effective_user.id if update.effective_user else None
    if not cfg.is_user_allowed(uid):
        if update.effective_message:
            await update.effective_message.reply_text("You are not allowed to use this bot.")
        return False
    return True


async def _admin_unknown_reply(msg) -> None:
    await msg.reply_text("Unknown command.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update, context):
        return
    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text(
        "Live Screener bot.\n\n"
        "You'll get a message automatically whenever a scan finds a hit "
        "(stock, setup, note).\n\n"
        "/next_schedule — when the next scan runs\n"
        "/today_signals — today's signals so far, as a CSV\n"
        "/run_now — run a scan immediately\n"
        "/help — this list"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update, context):
        return
    msg = update.effective_message
    if not msg:
        return
    cfg = _cfg(context)
    uid = update.effective_user.id if update.effective_user else None
    lines = [
        "/next_schedule — when the next scan runs",
        "/today_signals — today's signals so far, as a CSV",
        "/run_now — run a scan immediately, outside the schedule",
    ]
    if _is_admin(cfg, uid):
        lines += [
            "",
            "Administrator:",
            "/admin_add <user_id> — add a Telegram user id to the allowlist",
            "/admin_remove <user_id> — remove an id from the allowlist",
            "/admin_list — show admin id + full allowlist",
        ]
    await msg.reply_text("\n".join(lines))


async def cmd_next_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update, context):
        return
    msg = update.effective_message
    if not msg:
        return
    now = now_ist()
    nxt = next_scheduled_run(now)
    same_day = nxt.date() == now.date()
    when = nxt.strftime("%H:%M IST") if same_day else nxt.strftime("%a %d %b, %H:%M IST")
    await msg.reply_text(f"Next scan: {when}")


async def cmd_today_signals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update, context):
        return
    msg = update.effective_message
    if not msg:
        return
    path = signal_store.LIVE_SIGNALS_CSV
    if not path.is_file():
        await msg.reply_text("No signals recorded yet today.")
        return
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        df = pd.DataFrame()
    if df.empty:
        await msg.reply_text("No signals recorded yet today.")
        return
    data = path.read_bytes()
    await msg.reply_document(
        document=InputFile(data, filename=path.name),
        caption=f"{len(df)} row(s) so far today",
    )


async def cmd_run_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update, context):
        return
    msg = update.effective_message
    if not msg:
        return
    cfg = _cfg(context)
    lock: asyncio.Lock = context.application.bot_data["scan_lock"]
    if lock.locked():
        await msg.reply_text("A scan is already running — please wait for it to finish.")
        return
    async with lock:
        await _run_scan_and_push(context.bot, cfg)


async def cmd_admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    cfg = _cfg(context)
    uid = update.effective_user.id if update.effective_user else None
    if not _is_admin(cfg, uid):
        await _admin_unknown_reply(msg)
        return
    if not context.args:
        await msg.reply_text("Usage: /admin_add <user_id>")
        return
    try:
        new_id = int(context.args[0].strip())
    except ValueError:
        await msg.reply_text("Invalid user id.")
        return
    if new_id <= 0:
        await msg.reply_text("Invalid user id.")
        return
    lock: asyncio.Lock = context.application.bot_data["allowlist_lock"]
    async with lock:
        cur = read_extra_user_ids(cfg.project_root)
        if new_id in cur:
            await msg.reply_text(f"User {new_id} is already on the list.")
            return
        cur.add(new_id)
        write_extra_user_ids(cfg.project_root, cur)
    _log.info(f"allowlist add new_id={new_id} by_admin={uid}")
    await msg.reply_text(f"Added user {new_id}.")


async def cmd_admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    cfg = _cfg(context)
    uid = update.effective_user.id if update.effective_user else None
    if not _is_admin(cfg, uid):
        await _admin_unknown_reply(msg)
        return
    if not context.args:
        await msg.reply_text("Usage: /admin_remove <user_id>")
        return
    try:
        rid = int(context.args[0].strip())
    except ValueError:
        await msg.reply_text("Invalid user id.")
        return
    lock: asyncio.Lock = context.application.bot_data["allowlist_lock"]
    async with lock:
        cur = read_extra_user_ids(cfg.project_root)
        if rid not in cur:
            await msg.reply_text(
                "That id is not on the bot-managed list. "
                "(Ids listed only in ALLOWED_USER_IDS in .env must be edited there.)"
            )
            return
        cur.discard(rid)
        write_extra_user_ids(cfg.project_root, cur)
    _log.info(f"allowlist remove rid={rid} by_admin={uid}")
    await msg.reply_text(f"Removed user {rid}.")


async def cmd_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    cfg = _cfg(context)
    uid = update.effective_user.id if update.effective_user else None
    if not _is_admin(cfg, uid):
        await _admin_unknown_reply(msg)
        return
    env_ids = sorted(cfg.allowed_user_ids)
    disk = sorted(read_extra_user_ids(cfg.project_root))
    open_all = not env_ids and not disk
    lines = [
        "<b>Access control</b>",
        f"Admin id: <code>{cfg.admin_user_id}</code>",
        f"Open to any Telegram user: <b>{'yes' if open_all else 'no'}</b>",
        "",
        "ALLOWED_USER_IDS (.env): " + (html.escape(", ".join(str(x) for x in env_ids)) if env_ids else "(none)"),
        "Bot-managed list: " + (html.escape(", ".join(str(x) for x in disk)) if disk else "(none)"),
    ]
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


def build_application(cfg: TelegramConfig) -> Application:
    app = Application.builder().token(cfg.telegram_token).build()
    app.bot_data["config"] = cfg
    app.bot_data["allowlist_lock"] = asyncio.Lock()
    app.bot_data["scan_lock"] = asyncio.Lock()
    read_extra_user_ids(cfg.project_root)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("next_schedule", cmd_next_schedule))
    app.add_handler(CommandHandler("today_signals", cmd_today_signals))
    app.add_handler(CommandHandler("run_now", cmd_run_now))
    app.add_handler(CommandHandler("admin_add", cmd_admin_add))
    app.add_handler(CommandHandler("admin_remove", cmd_admin_remove))
    app.add_handler(CommandHandler("admin_list", cmd_admin_list))
    return app


async def _send_progress_messages(bot: Any, chat_ids: set[int]) -> dict[int, int]:
    """One 'starting…' message per recipient; returns {chat_id: message_id} for later edits."""
    handles: dict[int, int] = {}
    for chat_id in chat_ids:
        try:
            sent = await bot.send_message(chat_id=chat_id, text="\U0001f504 Scan starting…")
            handles[chat_id] = sent.message_id
        except Exception as exc:  # noqa: BLE001 — one bad chat id must not stop the others
            _log.warning(f"progress: failed to send initial message to chat_id={chat_id}: {exc}")
    return handles


async def _edit_progress_messages(bot: Any, handles: dict[int, int], text: str) -> None:
    for chat_id, message_id in handles.items():
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
        except Exception as exc:  # noqa: BLE001 — "not modified" and similar are harmless
            low = str(exc).lower()
            if "not modified" not in low:
                _log.warning(f"progress: failed to edit chat_id={chat_id}: {exc}")


async def _run_scan_and_push(bot: Any, cfg: TelegramConfig, show_progress: bool = True) -> pd.DataFrame:
    """Runs one scan, merges it into today's CSV, and pushes new-today hits. Returns those hits."""
    run_start = now_ist()
    loop = asyncio.get_running_loop()

    handles: dict[int, int] = {}
    if show_progress:
        handles = await _send_progress_messages(bot, cfg.broadcast_user_ids())

    last_edit_at = 0.0

    def on_progress(text: str) -> None:
        # Runs on the executor's worker thread (run_all is a blocking call) — must not
        # touch the bot/event loop directly, hence run_coroutine_threadsafe.
        nonlocal last_edit_at
        if not handles:
            return
        now_mono = time.monotonic()
        if now_mono - last_edit_at < PROGRESS_EDIT_THROTTLE_S:
            return
        last_edit_at = now_mono
        asyncio.run_coroutine_threadsafe(_edit_progress_messages(bot, handles, text), loop)

    try:
        _combined, hits = await loop.run_in_executor(
            None, functools.partial(run_all, on_progress=on_progress if show_progress else None)
        )
    except Exception:
        _log.exception("Scan failed")
        if handles:
            await _edit_progress_messages(bot, handles, "Scan failed — see output/scheduler.log.")
        return pd.DataFrame(columns=["setup", "symbol", "trigger_date", "trigger_close", "note"])

    run_end = now_ist()
    duration_s = (run_end - run_start).total_seconds()
    if duration_s > SLOW_RUN_WARNING_MINUTES * 60:
        _log.warning(
            f"Run took {duration_s / 60:.1f} min — longer than the {SLOW_RUN_WARNING_MINUTES}-min "
            "safety ceiling. The next run may be delayed or overlap."
        )
    if handles:
        summary = f"Scan complete ({duration_s:.0f}s). " + (
            f"{len(hits)} new hit(s) — sending now." if not hits.empty else "No new hits."
        )
        await _edit_progress_messages(bot, handles, summary)
    if not hits.empty:
        scan_time_label = run_start.strftime("%H:%M IST, %Y-%m-%d")
        await push_hits(bot, cfg.broadcast_user_ids(), hits, scan_time_label)
    return hits


async def _scan_loop(bot: Any, cfg: TelegramConfig, lock: asyncio.Lock) -> None:
    """Runs forever: sleeps through nights/weekends, scans+pushes every 15 min during the window."""
    while True:
        now = now_ist()

        if is_weekend(now) or now > today_at(now, WINDOW_END):
            nxt = next_scheduled_run(now)
            wait_s = max((nxt - now).total_seconds(), 0)
            _log.info(f"No scan due now ({now.isoformat()}); sleeping {wait_s / 60:.1f} min until {nxt.isoformat()}.")
            await asyncio.sleep(wait_s)
            continue

        ws = today_at(now, WINDOW_START)
        if now < ws:
            wait_s = max((ws - now).total_seconds(), 0)
            _log.info(f"Waiting {wait_s / 60:.1f} min for today's {WINDOW_START} open.")
            await asyncio.sleep(wait_s)
            continue

        run_start = now
        # If a /run_now request is mid-scan, wait for it rather than running concurrently
        # (see module docstring: merge_and_save has no file locking of its own).
        async with lock:
            await _run_scan_and_push(bot, cfg)

        we = today_at(run_start, WINDOW_END)
        next_run = run_start + timedelta(minutes=15)
        if next_run > we:
            _log.info("Done for today; sleeping until the next trading day's open.")
            continue

        sleep_s = max((next_run - now_ist()).total_seconds(), 0)
        await asyncio.sleep(sleep_s)


async def run_scheduler_with_bot(cfg: TelegramConfig) -> None:
    app = build_application(cfg)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    _log.info(
        f"Telegram bot polling started; admin_user_id={cfg.admin_user_id}. "
        "Scan loop running indefinitely (Ctrl+C to stop)."
    )
    try:
        await _scan_loop(app.bot, cfg, app.bot_data["scan_lock"])
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        _log.info("Telegram bot stopped.")
