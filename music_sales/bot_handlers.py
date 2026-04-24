from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.buy_constants import index_to_callback, sorted_buy_rows
from music_sales.catalog import discover_songs

logger = logging.getLogger(__name__)

GALLERY_SELECT_PREFIX = "g:s:"
GALLERY_PAGE_PREFIX = "g:p:"
GALLERY_PAGE_SIZE = 4
# Лимит подписи к фото в Telegram (символы; для HTML обычно хватает len() как грубой оценки).
MAX_PHOTO_CAPTION_LEN = 1024
UD_LAST_GALLERY_CONTROLS_MSG_ID = "gallery_last_controls_msg_id"
UD_LAST_GALLERY_BATCH_MSG_IDS = "gallery_last_batch_msg_ids"


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
        "Choose a track from the covers below.\n"
        "Tap the button under a cover to open full track card.\n"
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


def _load_tracks_from_tracks_py() -> list[dict]:
    """Загружает список треков из корневого `tracks.py` (описания для витрины)."""
    try:
        from tracks import TRACKS  # noqa: WPS433 — осознанный импорт из корня проекта

        return TRACKS
    except ImportError:
        return []


def _track_description_for_meta(song_meta: dict) -> str | None:
    """
    Находит текст описания из `tracks.py` для записи каталога `discover_songs()`.

    Сопоставляем по «основе имени файла» (stem): в каталоге и в tracks — .mp3.
    Дополнительно — по точному совпадению поля title с полем name из каталога.
    """
    file_stem = Path(str(song_meta.get("file", ""))).stem
    display_name = str(song_meta.get("name", "")).strip()
    tracks = _load_tracks_from_tracks_py()
    for t in tracks:
        audio_stem = Path(str(t.get("audio", ""))).stem
        if file_stem and audio_stem == file_stem:
            desc = t.get("description")
            if isinstance(desc, str) and desc.strip():
                return desc.strip()
    if display_name:
        for t in tracks:
            if str(t.get("title", "")).strip() == display_name:
                desc = t.get("description")
                if isinstance(desc, str) and desc.strip():
                    return desc.strip()
    return None


def _caption_html_for_track_card(*, song_name: str, price_usd: int, description: str | None) -> str:
    """HTML-подпись карточки трека (название, цена, описание); укладывается в лимит Telegram."""
    header_lines = [
        f"<b>{html.escape(song_name)}</b>",
        f"Price: <b>${price_usd} USD</b>",
    ]
    header = "\n".join(header_lines)
    if not description:
        return header

    desc_plain = description.strip()
    # В parse_mode="HTML" у Telegram переносы строк делаются обычным '\n', а не тегом <br>.
    desc_html = html.escape(desc_plain)
    full = f"{header}\n\n{desc_html}"
    if len(full) <= MAX_PHOTO_CAPTION_LEN:
        return full

    # Обрезаем только описание: после html.escape длина может вырасти, поэтому подбираем n по факту.
    ellipsis = "…"
    for n in range(len(desc_plain), 0, -1):
        fragment = desc_plain[:n]
        body = html.escape(fragment)
        suffix = ellipsis if n < len(desc_plain) else ""
        candidate = f"{header}\n\n{body}{suffix}"
        if len(candidate) <= MAX_PHOTO_CAPTION_LEN:
            return candidate
    return header


def _gallery_error_user_text_and_code(exc: Exception, *, has_cover: bool) -> tuple[str, str]:
    """
    Короткий и понятный текст ошибки для пользователя.

    Тексты интерфейса оставляем на английском по правилам проекта.
    """
    # Частые сетевые/временные ошибки Telegram API.
    if isinstance(exc, (TimedOut, NetworkError)):
        return "Temporary network issue while opening this track. Please try again.", "ERR_CARD_NETWORK"

    # Telegram BadRequest: обычно проблема с подписью, media или разметкой.
    if isinstance(exc, BadRequest):
        low = str(exc).lower()
        if "caption" in low or "parse" in low or "entities" in low:
            return "Track text is too long or invalid. Please try another track.", "ERR_CARD_CAPTION"
        if "photo" in low or "media" in low or "file" in low:
            return "Could not load the cover image. Please try again.", "ERR_CARD_TELEGRAM_MEDIA"
        return "Telegram could not open this track card. Please try again.", "ERR_CARD_TELEGRAM_BAD_REQUEST"

    # Локальная ошибка открытия файла обложки.
    if has_cover and isinstance(exc, OSError):
        return "Could not read the cover image file. Please try again.", "ERR_CARD_COVER_IO"

    return "Could not open this track card right now. Please try again.", "ERR_CARD_UNKNOWN"


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
            "`songs/` folder on the server (or set `AUDIO_SALES_DIR`), then try again."
        )
        return

    sorted_items = _sorted_song_items()
    await _send_gallery_page_cards_to_chat(
        context=context,
        chat_id=update.message.chat_id,
        sorted_items=sorted_items,
        page=0,
    )


async def _delete_previous_gallery_batch(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Удаляет предыдущий блок витрины (4 карточки + панель), чтобы не копить старые кнопки."""
    old_batch = context.user_data.get(UD_LAST_GALLERY_BATCH_MSG_IDS)
    if not isinstance(old_batch, list):
        return
    for item in old_batch:
        if not isinstance(item, dict):
            continue
        chat_id = item.get("chat_id")
        message_id = item.get("message_id")
        if not isinstance(chat_id, int) or not isinstance(message_id, int):
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            # Сообщение могло быть удалено вручную/устареть — это не критично.
            pass


async def _send_gallery_page_cards_to_chat(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sorted_items: list[tuple[str, dict]],
    page: int,
) -> None:
    """Показывает страницу витрины: 4 обложки (каждая с кнопкой) и одну панель Prev/Next."""
    total_items = len(sorted_items)
    page_count = _gallery_page_count(total_items)
    safe_page = max(0, min(page, page_count - 1))
    start = safe_page * GALLERY_PAGE_SIZE
    end = min(start + GALLERY_PAGE_SIZE, total_items)
    page_items = sorted_items[start:end]

    await _delete_previous_gallery_batch(context)

    sent_refs: list[dict] = []
    for absolute_idx, (_, song_meta) in enumerate(page_items, start=start):
        song_name = str(song_meta.get("name", f"Track {absolute_idx + 1}"))
        price_usd = int(song_meta.get("price_usd", 0) or 0)
        card_caption = f"<b>{html.escape(song_name)}</b>\nPrice: <b>${price_usd} USD</b>"
        select_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Open this track", callback_data=f"{GALLERY_SELECT_PREFIX}{absolute_idx:03d}")]]
        )

        cover_path = _cover_path_for_song(song_meta)
        if cover_path:
            with cover_path.open("rb") as photo:
                msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=card_caption,
                    parse_mode="HTML",
                    reply_markup=select_markup,
                )
        else:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=card_caption,
                parse_mode="HTML",
                reply_markup=select_markup,
            )
        sent_refs.append({"chat_id": chat_id, "message_id": msg.message_id})

    nav_markup = _gallery_markup(page=safe_page, sorted_items=sorted_items)
    nav_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=_gallery_text(page=safe_page, total_items=total_items),
        reply_markup=nav_markup,
    )
    sent_refs.append({"chat_id": chat_id, "message_id": nav_msg.message_id})
    context.user_data[UD_LAST_GALLERY_BATCH_MSG_IDS] = sent_refs
    context.user_data[UD_LAST_GALLERY_CONTROLS_MSG_ID] = nav_msg.message_id


async def _send_gallery_controls_for_page(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    sorted_items: list[tuple[str, dict]],
    page: int,
) -> None:
    """Совместимый хелпер: теперь отправляет целую страницу витрины в текущий чат."""
    if query.message is None:
        return
    await _send_gallery_page_cards_to_chat(
        context=context,
        chat_id=query.message.chat_id,
        sorted_items=sorted_items,
        page=page,
    )


async def gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик сетки: переключение страниц и открытие карточки конкретного трека."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    if query.data == "noop":
        await query.answer()
        return

    sorted_items = _sorted_song_items()
    if not sorted_items:
        await query.answer()
        if query.message:
            await query.message.reply_text("No tracks available right now.")
        return

    page_idx = _parse_gallery_index(query.data, GALLERY_PAGE_PREFIX)
    if page_idx is not None:
        await query.answer()
        await _send_gallery_controls_for_page(query, context, sorted_items=sorted_items, page=page_idx)
        return

    song_idx = _parse_gallery_index(query.data, GALLERY_SELECT_PREFIX)
    if song_idx is None or song_idx < 0 or song_idx >= len(sorted_items):
        await query.answer()
        if query.message:
            await query.message.reply_text("Unknown track in gallery. Please press /start again.")
        return

    song_id, song_meta = sorted_items[song_idx]
    song_name = str(song_meta.get("name", song_id))
    price_usd = int(song_meta.get("price_usd", 0) or 0)
    track_desc = _track_description_for_meta(song_meta)
    caption = _caption_html_for_track_card(song_name=song_name, price_usd=price_usd, description=track_desc)

    tg_callback_by_song_id: dict[str, str] = {}
    for idx, row in enumerate(sorted_buy_rows(_mp3_only_songs(discover_songs()))):
        tg_callback_by_song_id[row.song_id] = index_to_callback(idx)

    buttons = [[InlineKeyboardButton("Pay via external link", callback_data=song_id)]]
    tg_callback = tg_callback_by_song_id.get(song_id)
    if tg_callback:
        buttons.append([InlineKeyboardButton("Pay inside Telegram", callback_data=tg_callback)])
    markup = InlineKeyboardMarkup(buttons)

    cover_path = _cover_path_for_song(song_meta)
    try:
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
        # После открытия карточки заново показываем снизу панель галереи (4 трека + Prev/Next),
        # чтобы пользователю не приходилось скроллить вверх.
        current_page = song_idx // GALLERY_PAGE_SIZE
        await _send_gallery_controls_for_page(query, context, sorted_items=sorted_items, page=current_page)
        await query.answer()
    except Exception as e:
        user_text, err_code = _gallery_error_user_text_and_code(e, has_cover=cover_path is not None)
        logger.exception(
            "Failed to open track card: code=%s song_id=%s has_cover=%s error=%s",
            err_code,
            song_id,
            cover_path is not None,
            e,
        )
        try:
            await query.answer(
                user_text,
                show_alert=True,
            )
        except Exception:
            # Если callback уже подтверждён или устарел — продолжаем с обычным сообщением в чат.
            pass
        if query.message:
            await query.message.reply_text(user_text)


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
