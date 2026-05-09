"""
Админ-панель в Telegram: /admin, ConversationHandler, слои JSON + tracks_extra.

Тексты пользователю — на английском (правила проекта). Комментарии — на русском.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
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


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add New Track", callback_data="adm:add")],
            [InlineKeyboardButton("📋 View All Tracks", callback_data="adm:list")],
            [InlineKeyboardButton("✏️ Edit Track", callback_data="adm:editm")],
            [InlineKeyboardButton("🗑️ Delete Track", callback_data="adm:delm")],
            [InlineKeyboardButton("📊 Sales Statistics", callback_data="adm:stats")],
            [InlineKeyboardButton("❌ Close Admin", callback_data="adm:close")],
        ]
    )


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
        await q.message.reply_text("Main menu:", reply_markup=_main_menu_kb())
        return ST_MAIN

    if data == "adm:add":
        _log(uid or 0, "add_track_start")
        context.user_data["adm_draft"] = {}
        await q.message.reply_text("Step 1/6: Send the **track title** (plain text).")
        return ST_ADD_TITLE

    if data == "adm:list":
        return await _send_track_list(q.message, context, uid or 0)

    if data == "adm:stats":
        return await _send_sales_stats(q.message, uid or 0)

    if data == "adm:editm":
        await q.message.reply_text("Send the numeric **track id** to edit (see /admin → View All Tracks).")
        context.user_data["adm_mode"] = "edit_pick"
        return ST_EDIT_MENU

    if data == "adm:delm":
        await q.message.reply_text("Send the numeric **track id** to delete.")
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
            [InlineKeyboardButton("🗑️ Delete this track", callback_data=f"adm:dl:{tid}")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="adm:menu")],
        ]
        await q.message.reply_text(
            f"Track `{tid}` — {tr.get('title', '')[:60]}",
            parse_mode="Markdown",
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
            prompts = {
                "t": "Send new **title** (text).",
                "d": "Send new **description** (text).",
                "u": "Send **USD** price as whole dollars (e.g. 16).",
                "a": "Send new **Stripe USD payment link** (https://...).",
                "b": "Send new **Stripe SEK payment link** (https://...).",
                "c": "Upload a new **cover image** (JPG or PNG).",
                "m": "Upload a new **MP3** file.",
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
            f"Really delete track id **{tid}**?",
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
        await q.message.reply_text("Delete cancelled.", reply_markup=_main_menu_kb())
        return ST_MAIN

    if data.startswith("adm:svy"):
        await _save_new_track_confirmed(q.message, context, uid or 0)
        await q.message.reply_text("✅ Track added successfully!", reply_markup=_main_menu_kb())
        return ST_MAIN

    if data.startswith("adm:svn"):
        context.user_data.pop("adm_draft", None)
        _log(uid or 0, "add_track_cancelled")
        await q.message.reply_text("Cancelled.", reply_markup=_main_menu_kb())
        return ST_MAIN

    return ST_MAIN


async def _send_track_list(msg, context: ContextTypes.DEFAULT_TYPE, uid: int) -> int:
    from tracks import TRACKS

    lines = ["📋 Tracks (id — title — price):"]
    for t in sorted(TRACKS, key=lambda x: int(x["id"])):
        lines.append(f"{t['id']} — {t.get('title', '')[:40]} — {t.get('price', '')}")
    text = "\n".join(lines)[:4000]
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
    total = len(entries)
    per_track: dict[str, int] = {}
    for e in entries:
        key = str(e.get("track_title") or e.get("song_id") or "?")
        per_track[key] = per_track.get(key, 0) + 1
    top = sorted(per_track.items(), key=lambda x: -x[1])[:12]
    top_lines = "\n".join(f"• {k}: {v}" for k, v in top) or "(no sales yet)"
    tail = entries[-15:] if entries else []
    tail_lines = "\n".join(
        f"– {e.get('ts', '')[:19]} | {e.get('track_title', e.get('song_id', ''))} | {e.get('source', '')}"
        for e in reversed(tail)
    )
    text = f"📊 **Sales statistics**\n\nTotal checkouts logged: **{total}**\n\nPer track (top):\n{top_lines}\n\nLast events:\n{tail_lines or '—'}"
    _log(uid, "view_stats")
    await msg.reply_text(text[:4000], parse_mode="Markdown", reply_markup=_main_menu_kb())
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
    await update.message.reply_text("Step 2/6: Send **description** (long text is OK).")
    return ST_ADD_DESC


async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Please send a non-empty description.")
        return ST_ADD_DESC
    context.user_data["adm_draft"]["description"] = text
    await update.message.reply_text("Step 3/6: Send **USD** price as whole dollars (default 16 — just send 16).")
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
    await update.message.reply_text("Step 4/6: Send **SEK** price as whole kronor (default 169).")
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
    await update.message.reply_text("Step 5/6: Upload **cover image** (JPG or PNG).")
    return ST_ADD_COVER


async def add_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        return ConversationHandler.END
    if update.message and update.message.document:
        fn = (update.message.document.file_name or "").lower()
        mime = (update.message.document.mime_type or "").lower()
        if fn.endswith(".mp3") or mime.startswith("audio/"):
            await update.message.reply_text("That looks like an audio file. Please send an **image** for the cover.")
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
    await update.message.reply_text("Step 6/6: Upload the **MP3** file as a document.")
    return ST_ADD_MP3


async def add_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        return ConversationHandler.END
    doc = update.message.document if update.message else None
    if doc is None or not (doc.file_name or "").lower().endswith(".mp3"):
        await update.message.reply_text("Please send an **MP3** file as a document.")
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
    await update.message.reply_text("Creating Stripe product and payment links…")
    try:

        def _stripe_job() -> dict[str, str]:
            return create_product_and_payment_links(
                title=str(draft["title"]),
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
    from tracks import TRACKS

    new_id = max(int(t["id"]) for t in TRACKS) + 1 if TRACKS else 1
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
        await update.message.reply_text("Send a numeric track id.")
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
            f"Really delete track id **{tid}** — {tr.get('title', '')[:50]}?",
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
        [InlineKeyboardButton("⬅️ Menu", callback_data="adm:menu")],
    ]
    await update.message.reply_text(
        f"Editing track `{tid}` — choose field:",
        parse_mode="Markdown",
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
        await update.message.reply_text("Empty value, cancelled.")
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
            await update.message.reply_text("Send whole dollars as number.")
            return ST_EDIT_VALUE
        patch["price"] = f"${n}"
        patch["price_amount"] = n * 100
    elif field == "a":
        if not text.startswith("https://"):
            await update.message.reply_text("Must be https:// payment link")
            return ST_EDIT_VALUE
        patch["buy_url"] = text
    elif field == "b":
        if not text.startswith("https://"):
            await update.message.reply_text("Must be https:// payment link")
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
        await update.message.reply_text("Track disappeared. Menu.", reply_markup=_main_menu_kb())
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
                await update.message.reply_text("Send MP3 as document.")
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

