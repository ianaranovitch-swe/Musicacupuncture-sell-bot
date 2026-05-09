"""
Админ-панель в Telegram: /admin, ConversationHandler, слои JSON + tracks_extra.

Тексты пользователю — на английском (правила проекта). Комментарии — на русском.
"""

from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import stripe
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from music_sales import config
from music_sales.admin_log import append_admin_log
from music_sales.catalog import project_root
from music_sales.file_id_delivery import _file_ids_json_path, load_file_ids_from_disk
from music_sales.sales_log import read_sales_entries
from music_sales.stripe_track_products import create_product_and_payment_links, merge_file_id_json
from music_sales.tracks_admin_persist import (
    append_extra_track,
    read_deleted_ids,
    read_extras,
    remove_extra_track_by_id,
    sanitize_filename_stem,
    set_override,
    write_deleted_ids,
    write_extras,
)

logger = logging.getLogger(__name__)

# --- Состояния диалога ---
(
    ST_MAIN,
    ST_ADD_TITLE,
    ST_ADD_DESC,
    ST_ADD_USD,
    ST_ADD_SEK,
    ST_ADD_COVER,
    ST_ADD_MP3,
    ST_ADD_PREVIEW,
    ST_EDIT_MENU,
    ST_EDIT_VALUE,
    ST_EDIT_UPLOAD,
    ST_DEL_CONFIRM,
) = range(12)

_BUILTIN_IDS: set[int] | None = None


def _builtin_ids() -> set[int]:
    """Id треков из «вшитого» списка tracks.py (без extras)."""
    global _BUILTIN_IDS
    if _BUILTIN_IDS is not None:
        return _BUILTIN_IDS
    from tracks import _BUILTIN_TRACKS

    _BUILTIN_IDS = {int(t["id"]) for t in _BUILTIN_TRACKS}
    return _BUILTIN_IDS


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return int(user_id) in config.admin_telegram_ids()


def _log(uid: int, action: str, detail: dict[str, Any] | None = None) -> None:
    try:
        append_admin_log(user_id=uid, action=action, detail=detail)
    except Exception:
        logger.exception("admin_log failed")


def _sync_frontend_after_catalog_change(uid: int, log_action: str) -> None:
    """Обновить miniapp.html / website.html из TRACKS (после любого изменения каталога)."""
    try:
        from music_sales.frontend_catalog_sync import sync_frontend_html_catalog

        res = sync_frontend_html_catalog()
        for err in res.errors:
            _log(uid, "frontend_sync_error", {"msg": err})
        if res.written:
            _log(uid, log_action, {"frontend_files": len(res.written)})
    except Exception:
        logger.exception("frontend catalog sync")


def _move_file_id_alias(old_stem: str, new_stem: str) -> None:
    """Безопасно добавляем новый ключ в file_ids.json (старый оставляем как fallback)."""
    old_key = (old_stem or "").strip()
    new_key = (new_stem or "").strip()
    if not old_key or not new_key or old_key == new_key:
        return
    data = dict(load_file_ids_from_disk())
    fid = data.get(old_key)
    if not fid:
        return
    data[new_key] = fid
    _file_ids_json_path().write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


def _rename_track_media_files(track_id: int, uid: int) -> tuple[bool, str]:
    """
    Advanced: переименовать cover/audio под текущий title.
    Делает rollback, если какой-то rename не удался.
    """
    from tracks import get_track, reload_track_catalog

    tr = get_track(int(track_id))
    if tr is None:
        return False, "Track not found."

    title = str(tr.get("title") or "").strip() or "track"
    new_stem = sanitize_filename_stem(title)
    base = project_root()

    old_audio_rel = str(tr.get("audio") or "").strip()
    old_cover_rel = str(tr.get("cover") or "").strip()

    planned: list[tuple[Path, Path, str]] = []  # (src_abs, dst_abs, field)
    patch: dict[str, Any] = {}

    if old_audio_rel:
        src = base / old_audio_rel
        suffix = src.suffix or ".mp3"
        new_rel = f"songs/{new_stem}{suffix}"
        if new_rel != old_audio_rel:
            planned.append((src, base / new_rel, "audio"))
            patch["audio"] = new_rel

    if old_cover_rel:
        src = base / old_cover_rel
        suffix = src.suffix or ".jpg"
        new_rel = f"covers/{new_stem}{suffix}"
        if new_rel != old_cover_rel:
            planned.append((src, base / new_rel, "cover"))
            patch["cover"] = new_rel

    if not planned:
        return False, "Media filenames already match the current title."

    for src, dst, _ in planned:
        if not src.is_file():
            return False, f"File not found: {src.name}"
        if dst.exists() and dst.resolve() != src.resolve():
            return False, f"Target file already exists: {dst.name}"

    moved: list[tuple[Path, Path]] = []
    try:
        for src, dst, _ in planned:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            moved.append((src, dst))
    except OSError:
        for src, dst in reversed(moved):
            try:
                if dst.exists():
                    dst.rename(src)
            except OSError:
                pass
        return False, "Could not rename media files. No changes were kept."

    # Переносим alias file_id по stem MP3 (не удаляя старый ключ).
    if old_audio_rel and "audio" in patch:
        _move_file_id_alias(Path(old_audio_rel).stem, Path(str(patch["audio"])).stem)

    if int(track_id) in _builtin_ids():
        set_override(int(track_id), patch)
    else:
        items = read_extras()
        found = False
        for i, t in enumerate(items):
            if int(t.get("id", -1)) == int(track_id):
                items[i].update(patch)
                found = True
                break
        if not found:
            return False, "Extra track not found while saving updated paths."
        write_extras(items)

    reload_track_catalog()
    _sync_frontend_after_catalog_change(uid, "rename_media_frontend_sync")
    _log(uid, "rename_media_done", {"track_id": int(track_id), "patch": patch})
    return True, "✅ Media filenames updated safely."


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add New Track", callback_data="adm:add")],
            [InlineKeyboardButton("📋 View All Tracks", callback_data="adm:list")],
            [InlineKeyboardButton("✏️ Edit Track", callback_data="adm:editm")],
            [InlineKeyboardButton("🗑️ Delete Track", callback_data="adm:delm")],
            [InlineKeyboardButton("📊 Sales Statistics", callback_data="adm:stats")],
            [InlineKeyboardButton("🧾 Show FILE_IDS_JSON", callback_data="adm:fileids")],
            [InlineKeyboardButton("❌ Close Admin", callback_data="adm:close")],
        ]
    )


def _file_ids_json_env_payload() -> str:
    """
    Точное значение для Railway Variable FILE_IDS_JSON.
    Формат — компактный JSON в одну строку, как обычно хранят env-переменные.
    """
    data = dict(load_file_ids_from_disk())
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа /admin."""
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔️ Access denied")
        return ConversationHandler.END
    _log(uid, "admin_open")
    await update.message.reply_text(
        "🔐 Admin panel\nChoose an action:",
        reply_markup=_main_menu_kb(),
    )
    return ST_MAIN


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Admin panel closed.")
    elif update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            await update.callback_query.message.reply_text("Admin panel closed.")
    context.user_data.clear()
    return ConversationHandler.END


async def admin_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q is None or q.data is None or q.message is None:
        return ConversationHandler.END
    uid = q.from_user.id if q.from_user else None
    if not is_admin(uid):
        await q.answer("Access denied", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    data = q.data

    if data == "adm:close":
        _log(uid or 0, "admin_close")
        await q.message.reply_text("Admin panel closed.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "adm:menu":
        await q.message.reply_text("Admin menu:", reply_markup=_main_menu_kb())
        return ST_MAIN

    if data == "adm:add":
        _log(uid or 0, "add_track_start")
        context.user_data["adm_draft"] = {}
        await q.message.reply_text("Step 1/6: Send the track title (plain text).")
        return ST_ADD_TITLE

    if data == "adm:list":
        return await _send_track_list(q.message, context, uid or 0)

    if data == "adm:stats":
        return await _send_sales_stats(q.message, uid or 0)

    if data == "adm:fileids":
        payload = _file_ids_json_env_payload()
        context.user_data["adm_file_ids_payload"] = payload
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📋 Copy (show plain text)", callback_data="adm:fileids:copy")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="adm:fileids")],
                [InlineKeyboardButton("⬅️ Menu", callback_data="adm:menu")],
            ]
        )
        text = (
            "🧾 FILE_IDS_JSON (for Railway)\n\n"
            "Copy this value and paste it into Railway variable FILE_IDS_JSON.\n\n"
            f"<code>{html.escape(payload)}</code>"
        )
        # Если JSON слишком длинный для одного сообщения — отправляем fallback без code-блока.
        if len(text) > 3900:
            await q.message.reply_text(
                "FILE_IDS_JSON is too long for one formatted message.\n"
                "Tap Copy button below to get plain text in separate messages.",
                reply_markup=kb,
            )
        else:
            await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return ST_MAIN

    if data == "adm:fileids:copy":
        payload = str(context.user_data.get("adm_file_ids_payload") or _file_ids_json_env_payload())
        # В Telegram Bot API нет прямого clipboard API, поэтому отдаём plain text для ручного Copy.
        await q.message.reply_text(
            "Copy mode:\n"
            "1) Tap and hold the text below\n"
            "2) Choose Copy\n"
            "3) Paste into Railway FILE_IDS_JSON\n\n"
            f"{payload}"
        )
        return ST_MAIN

    if data == "adm:editm":
        await q.message.reply_text("Send the numeric track ID to edit (see /admin -> View All Tracks).")
        context.user_data["adm_mode"] = "edit_pick"
        return ST_EDIT_MENU

    if data == "adm:delm":
        await q.message.reply_text("Send the numeric track ID to delete.")
        context.user_data["adm_mode"] = "del_pick"
        return ST_EDIT_MENU

    if data.startswith("adm:pick:"):
        tid = int(data.split(":")[2])
        from tracks import get_track

        tr = get_track(tid)
        if tr is None:
            await q.message.reply_text("Unknown track.")
            return ST_MAIN
        kb_rows = [
            [InlineKeyboardButton("Title", callback_data=f"adm:ed:{tid}:t")],
            [InlineKeyboardButton("Description", callback_data=f"adm:ed:{tid}:d")],
            [InlineKeyboardButton("USD price", callback_data=f"adm:ed:{tid}:u")],
            [InlineKeyboardButton("Stripe USD link", callback_data=f"adm:ed:{tid}:a")],
            [InlineKeyboardButton("Stripe SEK link", callback_data=f"adm:ed:{tid}:b")],
            [InlineKeyboardButton("Replace cover", callback_data=f"adm:ed:{tid}:c")],
            [InlineKeyboardButton("Replace MP3", callback_data=f"adm:ed:{tid}:m")],
            [InlineKeyboardButton("🔁 Rename media files (advanced)", callback_data=f"adm:ed:{tid}:r")],
            [InlineKeyboardButton("🗑️ Delete this track", callback_data=f"adm:dl:{tid}")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="adm:menu")],
        ]
        await q.message.reply_text(
            f"Track {tid} - {tr.get('title', '')}",
            reply_markup=InlineKeyboardMarkup(kb_rows),
        )
        return ST_MAIN

    if data.startswith("adm:ed:"):
        # adm:ed:<id>:<field>
        parts = data.split(":")
        if len(parts) >= 4:
            tid = int(parts[2])
            field = parts[3]
            context.user_data["adm_edit_id"] = tid
            context.user_data["adm_edit_field"] = field
            _log(uid or 0, "edit_field_chosen", {"track_id": tid, "field": field})
            if field == "r":
                ok, text = _rename_track_media_files(tid, uid or 0)
                await q.message.reply_text(text, reply_markup=_main_menu_kb())
                return ST_MAIN
            prompts = {
                "t": "Send the new title (text).",
                "d": "Send the new description (text).",
                "u": "Send the USD price as whole dollars (e.g. 16).",
                "a": "Send the new Stripe USD payment link (https://...).",
                "b": "Send the new Stripe SEK payment link (https://...).",
                "c": "Upload the new cover image (JPG or PNG).",
                "m": "Upload the new MP3 file.",
            }
            await q.message.reply_text(prompts.get(field, "Send new value."))
            if field in ("c", "m"):
                return ST_EDIT_UPLOAD
            return ST_EDIT_VALUE
        return ST_MAIN

    if data.startswith("adm:dl:"):
        tid = int(data.split(":")[2])
        context.user_data["adm_del_id"] = tid
        await q.message.reply_text(
            f"Delete track ID {tid}?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Yes, delete", callback_data=f"adm:dy:{tid}"),
                        InlineKeyboardButton("❌ No", callback_data="adm:dn"),
                    ]
                ]
            ),
        )
        return ST_DEL_CONFIRM

    if data.startswith("adm:dy:"):
        tid = int(data.split(":")[2])
        await _execute_delete(q.message, context, uid or 0, tid, reply_markup=_main_menu_kb())
        return ST_MAIN

    if data == "adm:dn":
        await q.message.reply_text("Delete canceled.", reply_markup=_main_menu_kb())
        return ST_MAIN

    if data.startswith("adm:svy"):
        await _save_new_track_confirmed(q.message, context, uid or 0)
        await q.message.reply_text("✅ Track added successfully!", reply_markup=_main_menu_kb())
        return ST_MAIN

    if data.startswith("adm:svn"):
        context.user_data.pop("adm_draft", None)
        _log(uid or 0, "add_track_cancelled")
        await q.message.reply_text("Canceled.", reply_markup=_main_menu_kb())
        return ST_MAIN

    return ST_MAIN


async def _send_track_list(msg, context: ContextTypes.DEFAULT_TYPE, uid: int) -> int:
    from tracks import TRACKS

    lines = ["📋 Tracks (id — title — price):"]
    for t in sorted(TRACKS, key=lambda x: int(x["id"])):
        # Показываем полное имя, без обрезки.
        title = str(t.get("title", ""))
        lines.append(f"{t['id']} — {title} — {t.get('price', '')}")
    # Телеграм ограничивает длину сообщения, поэтому режем только общий размер.
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "..."
    rows = []
    row = []
    for t in sorted(TRACKS, key=lambda x: int(x["id"])):
        tid = int(t["id"])
        row.append(InlineKeyboardButton(f"✏️ {tid}", callback_data=f"adm:pick:{tid}"))
        if len(row) >= 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Menu", callback_data="adm:menu")])
    _log(uid, "list_tracks")
    # Без parse_mode: в названиях треков могут быть символы Markdown, из-за которых Telegram отклоняет сообщение.
    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))
    return ST_MAIN


async def _send_sales_stats(msg, uid: int) -> int:
    entries = read_sales_entries()

    # Берём только продажи (бесплатные выдачи считаются отдельно).
    sales = [e for e in entries if str(e.get("event_type") or "sale") == "sale"]
    free_downloads = sum(1 for e in entries if str(e.get("event_type") or "") == "free_download")

    def _entry_dt(e: dict[str, Any]) -> datetime:
        raw = str(e.get("ts") or "").strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return datetime.now(timezone.utc)

    def _entry_amount(e: dict[str, Any]) -> float:
        try:
            return float(e.get("amount") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _sum_by_currency(rows: list[dict[str, Any]]) -> tuple[float, float]:
        usd = 0.0
        sek = 0.0
        for e in rows:
            amount = _entry_amount(e)
            ccy = str(e.get("currency") or "").strip().upper()
            if ccy == "USD":
                usd += amount
            elif ccy == "SEK":
                sek += amount
        return usd, sek

    now = datetime.now(timezone.utc)
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    sales_today = [e for e in sales if _entry_dt(e).date() == today]
    sales_week = [e for e in sales if _entry_dt(e).date() >= week_start]
    sales_month = [e for e in sales if _entry_dt(e).date() >= month_start]
    sales_all = list(sales)

    usd_today, sek_today = _sum_by_currency(sales_today)
    usd_week, sek_week = _sum_by_currency(sales_week)
    usd_month, sek_month = _sum_by_currency(sales_month)
    usd_all, sek_all = _sum_by_currency(sales_all)

    per_track: dict[str, int] = {}
    for e in sales_all:
        key = str(e.get("track_title") or e.get("song_id") or "Unknown track")
        per_track[key] = per_track.get(key, 0) + 1
    top = sorted(per_track.items(), key=lambda x: -x[1])[:3]
    top_lines = "\n".join(f"{i}. {name} - {count} sales" for i, (name, count) in enumerate(top, start=1))
    if not top_lines:
        top_lines = "1. —\n2. —\n3. —"

    # Последние 7 дней: считаем продажи и выручку в USD (как в ТЗ).
    by_day_count: dict[str, int] = {}
    by_day_usd: dict[str, float] = {}
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        by_day_count[key] = 0
        by_day_usd[key] = 0.0
    for e in sales_all:
        d = _entry_dt(e).date()
        key = d.strftime("%Y-%m-%d")
        if key in by_day_count:
            by_day_count[key] += 1
            if str(e.get("currency") or "").strip().upper() == "USD":
                by_day_usd[key] += _entry_amount(e)
    last7_lines = "\n".join(
        f"{k}: {by_day_count[k]} sales - ${by_day_usd[k]:.2f}" for k in by_day_count
    )

    unique_days = { _entry_dt(e).date().isoformat() for e in sales_all } if sales_all else set()
    avg_per_day = (len(sales_all) / max(1, len(unique_days))) if sales_all else 0.0

    text = (
        "📊 SALES STATISTICS\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 TODAY:\n"
        f"• Sales: {len(sales_today)} tracks\n"
        f"• Revenue USD: ${usd_today:.2f}\n"
        f"• Revenue SEK: {sek_today:.2f} kr\n\n"
        "📅 THIS WEEK:\n"
        f"• Sales: {len(sales_week)} tracks\n"
        f"• Revenue USD: ${usd_week:.2f}\n"
        f"• Revenue SEK: {sek_week:.2f} kr\n\n"
        "📅 THIS MONTH:\n"
        f"• Sales: {len(sales_month)} tracks\n"
        f"• Revenue USD: ${usd_month:.2f}\n"
        f"• Revenue SEK: {sek_month:.2f} kr\n\n"
        "📅 ALL TIME:\n"
        f"• Total sales: {len(sales_all)} tracks\n"
        f"• Total USD: ${usd_all:.2f}\n"
        f"• Total SEK: {sek_all:.2f} kr\n"
        f"• Average per day: {avg_per_day:.2f} sales\n\n"
        "🏆 TOP TRACKS:\n"
        f"{top_lines}\n\n"
        "📈 LAST 7 DAYS:\n"
        f"{last7_lines}\n\n"
        "🎁 FREE DOWNLOADS:\n"
        f"Total free tracks sent: {free_downloads}"
    )
    _log(uid, "view_stats")
    await msg.reply_text(text[:4000], reply_markup=_main_menu_kb())
    return ST_MAIN


async def _execute_delete(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    tid: int,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    from tracks import reload_track_catalog

    tid = int(tid)
    if tid in _builtin_ids():
        ids = read_deleted_ids()
        if tid not in ids:
            ids.append(tid)
            write_deleted_ids(ids)
        _log(uid, "delete_builtin", {"track_id": tid})
    else:
        if remove_extra_track_by_id(tid):
            _log(uid, "delete_extra", {"track_id": tid})
        else:
            await msg.reply_text(f"No extra track with id {tid} in tracks_extra.json.")
            return
    reload_track_catalog()
    _sync_frontend_after_catalog_change(uid, "delete_track_frontend_sync")
    await msg.reply_text(
        "✅ Track deleted successfully (hidden or removed from extras).",
        reply_markup=reply_markup,
    )


async def _save_new_track_confirmed(msg, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    from tracks import reload_track_catalog

    draft = context.user_data.get("adm_draft") or {}
    track = draft.get("track")
    if not isinstance(track, dict):
        await msg.reply_text("Internal error: missing draft.")
        return
    append_extra_track(track)
    reload_track_catalog()
    _sync_frontend_after_catalog_change(uid, "add_track_frontend_sync")
    _log(uid, "add_track_saved", {"track_id": track.get("id")})
    context.user_data.pop("adm_draft", None)


async def add_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Please send a non-empty title.")
        return ST_ADD_TITLE
    context.user_data.setdefault("adm_draft", {})["title"] = text
    await update.message.reply_text("Step 2/6: Send the description (long text is OK).")
    return ST_ADD_DESC


async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Please send a non-empty description.")
        return ST_ADD_DESC
    context.user_data["adm_draft"]["description"] = text
    await update.message.reply_text("Step 3/6: Send the USD price as whole dollars (default 16; just send 16).")
    return ST_ADD_USD


async def add_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        return ConversationHandler.END
    raw = (update.message.text or "").strip() or "16"
    try:
        usd = max(1, int(raw))
    except ValueError:
        await update.message.reply_text("Send a number, e.g. 16")
        return ST_ADD_USD
    context.user_data["adm_draft"]["usd"] = usd
    await update.message.reply_text("Step 4/6: Send the SEK price as whole kronor (default 169).")
    return ST_ADD_SEK


async def add_sek(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        return ConversationHandler.END
    raw = (update.message.text or "").strip() or "169"
    try:
        sek = max(1, int(raw))
    except ValueError:
        await update.message.reply_text("Send a number, e.g. 169")
        return ST_ADD_SEK
    context.user_data["adm_draft"]["sek"] = sek
    await update.message.reply_text("Step 5/6: Upload the cover image (JPG or PNG).")
    return ST_ADD_COVER


async def add_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        return ConversationHandler.END
    if update.message and update.message.document:
        fn = (update.message.document.file_name or "").lower()
        mime = (update.message.document.mime_type or "").lower()
        if fn.endswith(".mp3") or mime.startswith("audio/"):
            await update.message.reply_text("That looks like an audio file. Please upload an image for the cover.")
            return ST_ADD_COVER
    draft = context.user_data.setdefault("adm_draft", {})
    title = str(draft.get("title") or "track")
    stem = sanitize_filename_stem(title)
    covers = project_root() / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    dest = covers / f"{stem}.jpg"
    try:
        if update.message.photo:
            photo = update.message.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            buf = io.BytesIO()
            await tg_file.download_to_memory(buf)
            buf.seek(0)
            from PIL import Image

            im = Image.open(buf).convert("RGB")
            im.save(dest, "JPEG", quality=92)
        elif update.message.document:
            doc = update.message.document
            tg_file = await context.bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await tg_file.download_to_memory(buf)
            buf.seek(0)
            from PIL import Image

            im = Image.open(buf).convert("RGB")
            im.save(dest, "JPEG", quality=92)
        else:
            await update.message.reply_text("Please send a photo or image document.")
            return ST_ADD_COVER
    except Exception:
        logger.exception("cover save")
        await update.message.reply_text("Could not read image. Try JPG/PNG again.")
        return ST_ADD_COVER
    draft["cover_rel"] = f"covers/{dest.name}"
    _log(uid, "add_cover_saved", {"path": str(draft["cover_rel"])})
    await update.message.reply_text("Step 6/6: Upload the MP3 file as a document.")
    return ST_ADD_MP3


async def add_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        return ConversationHandler.END
    doc = update.message.document if update.message else None
    if doc is None or not (doc.file_name or "").lower().endswith(".mp3"):
        await update.message.reply_text("Please upload an MP3 file as a document.")
        return ST_ADD_MP3
    draft = context.user_data.setdefault("adm_draft", {})
    title = str(draft.get("title") or "track")
    stem = sanitize_filename_stem(title)
    songs = project_root() / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    dest = songs / f"{stem}.mp3"
    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(custom_path=str(dest))
    draft["audio_rel"] = f"songs/{dest.name}"
    draft["stem"] = stem
    # file_id для доставки покупки
    merge_file_id_json(stem, doc.file_id)
    _log(uid, "add_mp3_saved", {"path": draft["audio_rel"]})
    from tracks import TRACKS

    # Новый id нужен заранее, чтобы записать его в metadata Stripe Payment Link.
    new_id = max(int(t["id"]) for t in TRACKS) + 1 if TRACKS else 1
    await update.message.reply_text("Creating Stripe product and payment links…")
    try:

        def _stripe_job() -> dict[str, str]:
            return create_product_and_payment_links(
                title=str(draft["title"]),
                description=str(draft.get("description") or ""),
                track_id=new_id,
                usd_whole=int(draft["usd"]),
                sek_whole=int(draft["sek"]),
            )

        links = await asyncio.to_thread(_stripe_job)
    except (stripe.error.StripeError, RuntimeError) as e:
        logger.exception("stripe create")
        await update.message.reply_text(
            f"Stripe error: {e}\nMP3 and cover are saved. Fix Stripe keys, then use Edit to add payment links, or start Add again.",
            reply_markup=_main_menu_kb(),
        )
        return ST_MAIN
    draft["stripe"] = links
    usd = int(draft["usd"])
    sek = int(draft["sek"])
    track = {
        "id": new_id,
        "short_title": f"🎵 {str(draft['title'])[:36]}",
        "title": str(draft["title"]),
        "description": str(draft["description"]),
        "price": f"${usd}",
        "price_amount": usd * 100,
        "cover": str(draft["cover_rel"]),
        "audio": str(draft["audio_rel"]),
        "buy_url": str(links.get("buy_url", "")),
        "buy_url_sek": str(links.get("buy_url_sek", "")),
    }
    draft["track"] = track
    preview = (
        f"✅ New track ready:\n"
        f"Title: {track['title']}\n"
        f"Price: ${usd} / {sek} kr\n"
        f"Stripe USD: {track['buy_url']}\n"
        f"Stripe SEK: {track['buy_url_sek']}\n"
        f"id={new_id}"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm & Save", callback_data="adm:svy"),
                InlineKeyboardButton("❌ Cancel", callback_data="adm:svn"),
            ]
        ]
    )
    await update.message.reply_text(preview, reply_markup=kb)
    return ST_ADD_PREVIEW


async def edit_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Первый ввод: id трека для правки."""
    uid = update.effective_user.id if update.effective_user else None
    if not is_admin(uid):
        return ConversationHandler.END
    mode = context.user_data.get("adm_mode")
    raw = (update.message.text or "").strip()
    if not raw.isdigit():
        await update.message.reply_text("Send a numeric track ID.")
        return ST_EDIT_MENU
    tid = int(raw)
    from tracks import get_track

    tr = get_track(tid)
    if tr is None:
        await update.message.reply_text("Unknown id. Try again.")
        return ST_EDIT_MENU
    if mode == "del_pick":
        context.user_data["adm_del_id"] = tid
        await update.message.reply_text(
            f"Delete track ID {tid} - {tr.get('title', '')[:50]}?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Yes", callback_data=f"adm:dy:{tid}"),
                        InlineKeyboardButton("❌ No", callback_data="adm:dn"),
                    ]
                ]
            ),
        )
        return ST_DEL_CONFIRM
    # edit
    kb_rows = [
        [InlineKeyboardButton("Title", callback_data=f"adm:ed:{tid}:t")],
        [InlineKeyboardButton("Description", callback_data=f"adm:ed:{tid}:d")],
        [InlineKeyboardButton("USD price", callback_data=f"adm:ed:{tid}:u")],
        [InlineKeyboardButton("Stripe USD link", callback_data=f"adm:ed:{tid}:a")],
        [InlineKeyboardButton("Stripe SEK link", callback_data=f"adm:ed:{tid}:b")],
        [InlineKeyboardButton("Replace cover", callback_data=f"adm:ed:{tid}:c")],
        [InlineKeyboardButton("Replace MP3", callback_data=f"adm:ed:{tid}:m")],
        [InlineKeyboardButton("🔁 Rename media files (advanced)", callback_data=f"adm:ed:{tid}:r")],
        [InlineKeyboardButton("⬅️ Menu", callback_data="adm:menu")],
    ]
    await update.message.reply_text(
        f"Editing track {tid} - choose a field:",
        reply_markup=InlineKeyboardMarkup(kb_rows),
    )
    return ST_MAIN


async def edit_value_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from tracks import reload_track_catalog

    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        return ConversationHandler.END
    tid = int(context.user_data.get("adm_edit_id", 0))
    field = str(context.user_data.get("adm_edit_field", ""))
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Empty value. Canceled.")
        return ST_MAIN
    patch: dict[str, Any] = {}
    if field == "t":
        patch["title"] = text
        patch["short_title"] = f"🎵 {text[:36]}"
    elif field == "d":
        patch["description"] = text
    elif field == "u":
        try:
            n = int(text)
        except ValueError:
            await update.message.reply_text("Send whole dollars as a number.")
            return ST_EDIT_VALUE
        patch["price"] = f"${n}"
        patch["price_amount"] = n * 100
    elif field == "a":
        if not text.startswith("https://"):
            await update.message.reply_text("The payment link must start with https://")
            return ST_EDIT_VALUE
        patch["buy_url"] = text
    elif field == "b":
        if not text.startswith("https://"):
            await update.message.reply_text("The payment link must start with https://")
            return ST_EDIT_VALUE
        patch["buy_url_sek"] = text
    else:
        await update.message.reply_text("Unknown field.")
        return ST_MAIN
    if tid in _builtin_ids():
        set_override(tid, patch)
    else:
        # extra track — правим запись в tracks_extra.json
        items = read_extras()
        found = False
        for i, t in enumerate(items):
            if int(t.get("id", -1)) == tid:
                items[i].update(patch)
                found = True
                break
        if not found:
            await update.message.reply_text("Extra track not found.")
            return ST_MAIN
        write_extras(items)
    reload_track_catalog()
    _sync_frontend_after_catalog_change(uid, "edit_track_frontend_sync")
    _log(uid, "edit_saved", {"track_id": tid, "field": field})
    if field == "t":
        await update.message.reply_text(f"✅ Title updated: {text}", reply_markup=_main_menu_kb())
    else:
        await update.message.reply_text("✅ Saved.", reply_markup=_main_menu_kb())
    return ST_MAIN


async def edit_upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from tracks import get_track, reload_track_catalog

    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        return ConversationHandler.END
    tid = int(context.user_data.get("adm_edit_id", 0))
    field = str(context.user_data.get("adm_edit_field", ""))
    tr = get_track(tid)
    if tr is None:
        await update.message.reply_text("Track not found anymore. Returning to menu.", reply_markup=_main_menu_kb())
        return ST_MAIN
    title = str(tr.get("title", "track"))
    stem = sanitize_filename_stem(Path(str(tr.get("audio", ""))).stem or title)
    try:
        if field == "c":
            covers = project_root() / "covers"
            covers.mkdir(parents=True, exist_ok=True)
            dest = covers / f"{stem}.jpg"
            if update.message.photo:
                photo = update.message.photo[-1]
                tg_file = await context.bot.get_file(photo.file_id)
                buf = io.BytesIO()
                await tg_file.download_to_memory(buf)
                buf.seek(0)
                from PIL import Image

                im = Image.open(buf).convert("RGB")
                im.save(dest, "JPEG", quality=92)
            elif update.message.document:
                tg_file = await context.bot.get_file(update.message.document.file_id)
                buf = io.BytesIO()
                await tg_file.download_to_memory(buf)
                buf.seek(0)
                from PIL import Image

                im = Image.open(buf).convert("RGB")
                im.save(dest, "JPEG", quality=92)
            else:
                await update.message.reply_text("Send a cover image.")
                return ST_EDIT_UPLOAD
            patch = {"cover": f"covers/{dest.name}"}
        elif field == "m":
            doc = update.message.document
            if doc is None or not (doc.file_name or "").lower().endswith(".mp3"):
                await update.message.reply_text("Send an MP3 file as a document.")
                return ST_EDIT_UPLOAD
            songs = project_root() / "songs"
            songs.mkdir(parents=True, exist_ok=True)
            dest = songs / f"{stem}.mp3"
            tg_file = await context.bot.get_file(doc.file_id)
            await tg_file.download_to_drive(custom_path=str(dest))
            merge_file_id_json(stem, doc.file_id)
            patch = {"audio": f"songs/{dest.name}"}
        else:
            return ST_MAIN
    except Exception:
        logger.exception("edit upload")
        await update.message.reply_text("Failed to process file.")
        return ST_EDIT_UPLOAD
    if tid in _builtin_ids():
        set_override(tid, patch)
    else:
        items = read_extras()
        for i, t in enumerate(items):
            if int(t.get("id", -1)) == tid:
                items[i].update(patch)
                break
        write_extras(items)
    reload_track_catalog()
    _sync_frontend_after_catalog_change(uid, "edit_file_frontend_sync")
    _log(uid, "edit_file_saved", {"track_id": tid, "field": field})
    await update.message.reply_text("✅ File updated.", reply_markup=_main_menu_kb())
    return ST_MAIN


def build_admin_conversation_handler() -> ConversationHandler:
    """Собираем ConversationHandler (подключается в bot.py)."""
    return ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ST_MAIN: [CallbackQueryHandler(admin_main_callback, pattern=r"^adm:")],
            ST_ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            ST_ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)],
            ST_ADD_USD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_usd)],
            ST_ADD_SEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sek)],
            ST_ADD_COVER: [
                MessageHandler(filters.PHOTO, add_cover),
                MessageHandler(filters.Document.ALL, add_cover),
            ],
            ST_ADD_MP3: [MessageHandler(filters.Document.FileExtension("mp3"), add_mp3)],
            ST_ADD_PREVIEW: [
                CallbackQueryHandler(admin_main_callback, pattern=r"^adm:sv"),
            ],
            ST_EDIT_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_menu_text)],
            ST_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_text)],
            ST_EDIT_UPLOAD: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, edit_upload_file),
                MessageHandler(filters.Document.FileExtension("mp3"), edit_upload_file),
            ],
            ST_DEL_CONFIRM: [CallbackQueryHandler(admin_main_callback, pattern=r"^adm:d")],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        name="admin_conversation",
        per_chat=True,
        per_user=True,
        allow_reentry=True,
    )

