from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path

import requests
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    User,
    WebAppInfo,
)
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.catalog import discover_songs
from music_sales.owner_notify import notify_owner_async

logger = logging.getLogger(__name__)

GALLERY_SELECT_PREFIX = "g:s:"
GALLERY_NEXT_PREFIX = "g:n:"
PAY_CURRENCY_PREFIX = "pay:"
GALLERY_PAGE_SIZE = 4
# Лимит подписи к фото в Telegram (символы; для HTML обычно хватает len() как грубой оценки).
MAX_PHOTO_CAPTION_LEN = 1024
UD_LAST_GALLERY_CONTROLS_MSG_ID = "gallery_last_controls_msg_id"
UD_LAST_GALLERY_BATCH_MSG_IDS = "gallery_last_batch_msg_ids"
UD_LAST_GALLERY_SHOWN_PAGE = "gallery_last_shown_page"
UD_LAST_GALLERY_CARD_MSG_ID = "gallery_last_card_msg_id"
UD_PENDING_CHECKOUT_SONG_ID = "pending_checkout_song_id"

SUPPORTED_CURRENCIES = ("usd", "eur", "sek")


async def notify_owner_about_visitor(context: ContextTypes.DEFAULT_TYPE, visitor: User) -> None:
    """Отправить владельцу событие о запуске бота без показа ID пользователя."""
    await notify_owner_async(
        context,
        actor=visitor,
        event="Bot started",
    )


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


def _miniapp_store_row() -> list[InlineKeyboardButton] | None:
    """Одна строка с Mini App, если задан валидный HTTPS URL (требование Telegram)."""
    url = config.resolved_miniapp_url()
    if not url.startswith("https://"):
        return None
    return [InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=url))]


async def _send_miniapp_store_opener_if_configured(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Первое сообщение при /start: кнопка WebApp (тексты UI на английском)."""
    if update.message is None:
        return
    row = _miniapp_store_row()
    if not row:
        return
    await update.message.reply_text(
        "Welcome! Tap the button below to open the Music Store.",
        reply_markup=InlineKeyboardMarkup([row]),
    )


def _full_catalog_markup(
    *,
    sorted_items: list[tuple[str, dict]],
    current_idx: int,
    current_song_id: str,
) -> InlineKeyboardMarkup:
    """Клавиатура каталога: Buy для текущего трека + 16 кнопок + NEXT."""
    grid_rows: list[list[InlineKeyboardButton]] = []
    mini_row = _miniapp_store_row()
    if mini_row:
        grid_rows.append(mini_row)
    # Кнопка покупки текущего трека всегда сверху, рядом с карточкой/обложкой.
    grid_rows.append([InlineKeyboardButton("💳 Buy this track", callback_data=current_song_id)])
    for absolute_idx, (_, meta) in enumerate(sorted_items):
        label = str(meta.get("name", f"Track {absolute_idx + 1}"))
        grid_rows.append(
            [
                InlineKeyboardButton(
                    f"🎵 {label}",
                    callback_data=f"{GALLERY_SELECT_PREFIX}{absolute_idx:03d}",
                )
            ]
        )

    next_idx = (current_idx + 1) % len(sorted_items)
    grid_rows.append([InlineKeyboardButton("NEXT", callback_data=f"{GALLERY_NEXT_PREFIX}{next_idx:03d}")])
    return InlineKeyboardMarkup(grid_rows)


def _gallery_markup(page: int, sorted_items: list[tuple[str, dict]]) -> InlineKeyboardMarkup:
    total_items = len(sorted_items)
    page_count = _gallery_page_count(total_items)
    shown_page = max(0, min(page, page_count - 1))
    # Внизу показываем кнопки следующей страницы, чтобы не дублировать обложки сверху.
    select_page = (shown_page + 1) % page_count if page_count > 1 else shown_page
    start = select_page * GALLERY_PAGE_SIZE
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
    if shown_page > 0:
        nav_row.append(InlineKeyboardButton("Prev", callback_data=f"{GALLERY_PAGE_PREFIX}{shown_page - 1:03d}"))
    nav_row.append(InlineKeyboardButton(f"Page {shown_page + 1}/{page_count}", callback_data="noop"))
    if shown_page < page_count - 1:
        nav_row.append(InlineKeyboardButton("Next", callback_data=f"{GALLERY_PAGE_PREFIX}{shown_page + 1:03d}"))
    grid_rows.append(nav_row)

    return InlineKeyboardMarkup(grid_rows)


def _gallery_text(page: int, total_items: int) -> str:
    page_count = _gallery_page_count(total_items)
    safe_page = max(0, min(page, page_count - 1))
    return (
        "Choose a track from the covers below.\n"
        "Tap the button under a cover to open full track card.\n"
        "Bottom buttons show the next 4 tracks.\n"
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


def _user_display_name(user: User | None) -> str:
    """Безопасное имя пользователя для логов/метаданных платежа."""
    if user is None:
        return "Unknown user"
    if user.username:
        return f"@{user.username}"
    full = " ".join(x for x in (user.first_name, user.last_name or "") if x).strip()
    return full or "Unknown user"


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
    # Сначала приветствие с WebApp — витрина открывается одним тапом.
    await _send_miniapp_store_opener_if_configured(update, context)
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
    await _send_single_track_card(context=context, chat_id=update.message.chat_id, sorted_items=sorted_items, song_idx=0)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает краткую справку по функциям бота и быстрые кнопки-команды."""
    if update.message is None:
        return

    lines = [
        "This bot sells MP3 tracks and sends paid audio in Telegram.",
        "",
        "Commands:",
        "• /start — open the track catalog with covers",
        "• /buy — open the compact buy list",
        "• /help — show this help message",
        "• /health — owner/developer diagnostics only",
        "",
        "How to buy:",
        "1) Choose a track in /start or /buy",
        "2) Choose currency/payment method",
        "3) Open Stripe checkout and complete payment",
        "",
        "Tip: if checkout opened in background, tap Buy again and open the latest checkout link/button.",
    ]

    # Кнопки помогают быстро отправлять команды без ручного ввода.
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("/start"), KeyboardButton("/buy")],
            [KeyboardButton("/help"), KeyboardButton("/health")],
        ],
        resize_keyboard=True,
    )
    await update.message.reply_text("\n".join(lines), reply_markup=keyboard)


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
        track_desc = _track_description_for_meta(song_meta)
        card_caption = _caption_html_for_track_card(
            song_name=song_name,
            price_usd=price_usd,
            description=track_desc,
        )
        select_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Buy this track", callback_data=f"{GALLERY_SELECT_PREFIX}{absolute_idx:03d}")]]
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
    context.user_data[UD_LAST_GALLERY_SHOWN_PAGE] = safe_page


async def _send_single_track_card(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sorted_items: list[tuple[str, dict]],
    song_idx: int,
) -> None:
    """Показывает только одну карточку трека и полную клавиатуру из 16 кнопок + NEXT."""
    if not sorted_items:
        await context.bot.send_message(chat_id=chat_id, text="No tracks available right now.")
        return

    safe_idx = max(0, min(song_idx, len(sorted_items) - 1))
    song_id, song_meta = sorted_items[safe_idx]
    song_name = str(song_meta.get("name", song_id))
    price_usd = int(song_meta.get("price_usd", 0) or 0)
    track_desc = _track_description_for_meta(song_meta)
    caption = _caption_html_for_track_card(song_name=song_name, price_usd=price_usd, description=track_desc)
    markup = _full_catalog_markup(
        sorted_items=sorted_items,
        current_idx=safe_idx,
        current_song_id=song_id,
    )

    last_msg_id = context.user_data.get(UD_LAST_GALLERY_CARD_MSG_ID)
    if isinstance(last_msg_id, int):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_msg_id)
        except Exception:
            pass

    cover_path = _cover_path_for_song(song_meta)
    if cover_path:
        with cover_path.open("rb") as photo:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
    else:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
    context.user_data[UD_LAST_GALLERY_CARD_MSG_ID] = msg.message_id


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
    """Обработчик витрины: выбор трека и кнопка NEXT (по одному треку за раз)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    sorted_items = _sorted_song_items()
    if not sorted_items:
        await query.answer()
        if query.message:
            await query.message.reply_text("No tracks available right now.")
        return

    song_idx = _parse_gallery_index(query.data, GALLERY_SELECT_PREFIX)
    if song_idx is None:
        song_idx = _parse_gallery_index(query.data, GALLERY_NEXT_PREFIX)
    if song_idx is None or song_idx < 0 or song_idx >= len(sorted_items):
        await query.answer()
        if query.message:
            await query.message.reply_text("Unknown track in gallery. Please press /start again.")
        return

    song_id, song_meta = sorted_items[song_idx]
    song_name = str(song_meta.get("name", song_id))
    price_usd = int(song_meta.get("price_usd", 0) or 0)
    track_desc = _track_description_for_meta(song_meta)
    try:
        # Сообщаем владельцу о клике по конкретному треку.
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Track clicked",
            song_name=song_name,
        )
        if query.message is not None and query.message.chat is not None:
            await _send_single_track_card(
                context=context,
                chat_id=query.message.chat.id,
                sorted_items=sorted_items,
                song_idx=song_idx,
            )
        await query.answer()
    except Exception as e:
        user_text, err_code = _gallery_error_user_text_and_code(e, has_cover=False)
        logger.exception(
            "Failed to open track card: code=%s song_id=%s has_cover=%s error=%s",
            err_code,
            song_id,
            False,
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

    user_id = query.from_user.id
    callback_data = str(query.data or "")
    songs = discover_songs()

    # Шаг 1: пользователь нажал Buy у текущего трека — просим выбрать валюту.
    if callback_data in songs:
        context.user_data[UD_PENDING_CHECKOUT_SONG_ID] = callback_data
        if query.message:
            await query.message.reply_text(
                "Choose your payment currency:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("USD", callback_data=f"{PAY_CURRENCY_PREFIX}usd")],
                        [InlineKeyboardButton("EUR", callback_data=f"{PAY_CURRENCY_PREFIX}eur")],
                        [InlineKeyboardButton("SEK", callback_data=f"{PAY_CURRENCY_PREFIX}sek")],
                    ]
                ),
            )
        return

    if not callback_data.startswith(PAY_CURRENCY_PREFIX):
        return
    currency = callback_data.split(":", 1)[1].lower()
    if currency not in SUPPORTED_CURRENCIES:
        if query.message:
            await query.message.reply_text("Unknown currency. Please try again.")
        return

    song_id = str(context.user_data.get(UD_PENDING_CHECKOUT_SONG_ID) or "")
    logger.info("Checkout currency chosen: user_id=%s song_id=%s currency=%s", user_id, song_id, currency)

    if not song_id or song_id not in songs:
        if query.message:
            await query.message.reply_text("Please choose a track first.")
        return

    try:
        response = await asyncio.to_thread(
            lambda: requests.post(
                f"{backend_url}/create-checkout",
                json={
                    "song_id": song_id,
                    "telegram_id": user_id,
                    "telegram_name": _user_display_name(query.from_user),
                    "currency": currency,
                },
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
    # Отправляем URL-кнопку, чтобы пользователь сразу открывал Stripe Checkout.
    await query.message.reply_text(
        "Tap to open secure Stripe checkout:\n"
        f"{payment_url}\n\n"
        "If it opened in background, tap the button again.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("💳 Open Stripe Checkout", url=payment_url)]]
        ),
    )
