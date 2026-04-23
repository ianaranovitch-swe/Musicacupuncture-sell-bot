from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.buy_constants import index_to_callback, sorted_buy_rows
from music_sales.catalog import discover_songs

logger = logging.getLogger(__name__)

GALLERY_SELECT_PREFIX = "g:s:"
GALLERY_PAGE_PREFIX = "g:p:"
GALLERY_PAGE_SIZE = 4


def _format_visitor_notice(visitor: User) -> str:
    """Короткое HTML-сообщение владельцу бота."""
    uname = f"@{visitor.username}" if visitor.username else "(no username)"
    name = " ".join(x for x in (visitor.first_name, visitor.last_name or "") if x).strip() or "—"
    return (
        "🛎 <b>Someone opened the bot</b> (/start)\n\n"
        f"<b>User ID:</b> <code>{visitor.id}</code>\n"
        f"<b>Name:</b> {html.escape(name)}\n"
        f"<b>Username:</b> {html.escape(uname)}"
    )


async def notify_owner_about_visitor(context: ContextTypes.DEFAULT_TYPE, visitor: User) -> None:
    """Отправить владельцу личное сообщение, когда пользователь запустил бота (/start)."""
    owner_id = config.owner_telegram_id_int()
    if owner_id is None:
        return
    if visitor.id == owner_id:
        return
    text = _format_visitor_notice(visitor)
    try:
        await context.bot.send_message(
            chat_id=owner_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info("Owner %s notified about visitor %s", owner_id, visitor.id)
    except Exception as e:
        logger.warning("Could not notify owner %s: %s", owner_id, e)


def _mp3_only_songs(all_songs: dict) -> dict:
    """Оставить только MP3, чтобы кнопка Telegram Payments вела в валидный сценарий."""
    out: dict = {}
    for song_id, meta in all_songs.items():
        file_path = str(meta.get("file", "")).lower()
        if file_path.endswith(".mp3"):
            out[song_id] = meta
    return out


def _cover_path_for_song(song_meta: dict) -> Path | None:
    """Найти файл обложки в папке covers по имени аудио (одинаковая основа имени)."""
    file_path = str(song_meta.get("file", ""))
    stem = Path(file_path).stem
    if not stem:
        return None

    covers_dir = Path(__file__).resolve().parent.parent / "covers"
    if not covers_dir.is_dir():
        return None

    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = covers_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _sorted_song_items() -> list[tuple[str, dict]]:
    songs = discover_songs()
    return sorted(songs.items(), key=lambda kv: kv[1]["name"].lower())


def _gallery_page_count(total_items: int) -> int:
    return max(1, (total_items + GALLERY_PAGE_SIZE - 1) // GALLERY_PAGE_SIZE)


def _gallery_markup(page: int, sorted_items: list[tuple[str, dict]]) -> InlineKeyboardMarkup:
    total_items = len(sorted_items)
    page_count = _gallery_page_count(total_items)
    safe_page = max(0, min(page, page_count - 1))
    start = safe_page * GALLERY_PAGE_SIZE
    end = min(start + GALLERY_PAGE_SIZE, total_items)
    page_items = sorted_items[start:end]

    grid_rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for absolute_idx, (_, meta) in enumerate(page_items, start=start):
        label = str(meta.get("name", f"Track {absolute_idx + 1}"))
        short_label = label if len(label) <= 24 else f"{label[:23]}…"
        row.append(
            InlineKeyboardButton(
                f"{absolute_idx + 1}. {short_label}",
                callback_data=f"{GALLERY_SELECT_PREFIX}{absolute_idx:03d}",
            )
        )
        if len(row) == 2:
            grid_rows.append(row)
            row = []
    if row:
        grid_rows.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton("Prev", callback_data=f"{GALLERY_PAGE_PREFIX}{safe_page - 1:03d}"))
    nav_row.append(InlineKeyboardButton(f"Page {safe_page + 1}/{page_count}", callback_data="noop"))
    if safe_page < page_count - 1:
        nav_row.append(InlineKeyboardButton("Next", callback_data=f"{GALLERY_PAGE_PREFIX}{safe_page + 1:03d}"))
    grid_rows.append(nav_row)

    return InlineKeyboardMarkup(grid_rows)


def _gallery_text(page: int, total_items: int) -> str:
    page_count = _gallery_page_count(total_items)
    safe_page = max(0, min(page, page_count - 1))
    return (
        "Choose a track from the 2x2 grid.\n"
        "Open a track card, then pay by Stripe link or inside Telegram.\n"
        f"Tracks: {total_items} | Page: {safe_page + 1}/{page_count}\n\n"
        "Alternative list mode: /buy"
    )


def _parse_gallery_index(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    tail = data[len(prefix) :]
    if not tail.isdigit():
        return None
    return int(tail)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user = update.effective_user
    if user is not None:
        logger.info("/start from user_id=%s username=%s", user.id, user.username or "-")
        await notify_owner_about_visitor(context, user)
    songs = discover_songs()
    if not songs:
        await update.message.reply_text(
            "No tracks available yet. Add audio files (.mp3, .wav, .m4a, …) to the "
            "SONGS folder on the server, then try again."
        )
        return

    sorted_items = _sorted_song_items()
    await update.message.reply_text(
        _gallery_text(page=0, total_items=len(sorted_items)),
        reply_markup=_gallery_markup(page=0, sorted_items=sorted_items),
    )


async def gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик сетки: переключение страниц и открытие карточки конкретного трека."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    if query.data == "noop":
        return

    sorted_items = _sorted_song_items()
    if not sorted_items:
        if query.message:
            await query.message.reply_text("No tracks available right now.")
        return

    page_idx = _parse_gallery_index(query.data, GALLERY_PAGE_PREFIX)
    if page_idx is not None:
        if query.message:
            await query.message.edit_text(
                _gallery_text(page=page_idx, total_items=len(sorted_items)),
                reply_markup=_gallery_markup(page=page_idx, sorted_items=sorted_items),
            )
        return

    song_idx = _parse_gallery_index(query.data, GALLERY_SELECT_PREFIX)
    if song_idx is None or song_idx < 0 or song_idx >= len(sorted_items):
        if query.message:
            await query.message.reply_text("Unknown track in gallery. Please press /start again.")
        return

    song_id, song_meta = sorted_items[song_idx]
    song_name = str(song_meta.get("name", song_id))
    price_usd = int(song_meta.get("price_usd", 0) or 0)
    caption = f"<b>{html.escape(song_name)}</b>\nPrice: <b>${price_usd} USD</b>"

    tg_callback_by_song_id: dict[str, str] = {}
    for idx, row in enumerate(sorted_buy_rows(_mp3_only_songs(discover_songs()))):
        tg_callback_by_song_id[row.song_id] = index_to_callback(idx)

    buttons = [[InlineKeyboardButton("Pay via external link", callback_data=song_id)]]
    tg_callback = tg_callback_by_song_id.get(song_id)
    if tg_callback:
        buttons.append([InlineKeyboardButton("Pay inside Telegram", callback_data=tg_callback)])
    markup = InlineKeyboardMarkup(buttons)

    cover_path = _cover_path_for_song(song_meta)
    if cover_path and query.message is not None and query.message.chat is not None:
        with cover_path.open("rb") as photo:
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
    elif query.message:
        await query.message.reply_text(
            caption,
            parse_mode="HTML",
            reply_markup=markup,
        )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE, backend_url: str) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    song_id = query.data
    user_id = query.from_user.id
    logger.info("Checkout button: user_id=%s song_id=%s", user_id, song_id)

    if song_id not in discover_songs():
        if query.message:
            await query.message.reply_text("This track is not available anymore.")
        return

    try:
        response = await asyncio.to_thread(
            lambda: requests.post(
                f"{backend_url}/create-checkout",
                json={"song_id": song_id, "telegram_id": user_id},
                timeout=30,
            )
        )
        response.raise_for_status()
        payment_url = response.json().get("url")
    except requests.RequestException as e:
        logger.exception("Checkout request failed: %s", e)
        payment_url = None
    except ValueError as e:
        logger.exception("Invalid JSON from backend: %s", e)
        payment_url = None

    if query.message is None:
        logger.warning("callback_query.message is None")
        return

    if not payment_url:
        logger.warning("No payment URL for user_id=%s song_id=%s", user_id, song_id)
        await query.message.reply_text(
            "Could not create a payment right now. Please try again later."
        )
        return

    logger.info("Checkout URL sent to user_id=%s song_id=%s", user_id, song_id)
    await query.message.reply_text(f"Click here to pay:\n{payment_url}")
