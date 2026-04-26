"""
Simple Telegram bot: list 16 tracks from tracks.py, show cover + text, buy link when set.

Run:  python bot.py

Needs in .env: BOT_TOKEN (and STRIPE_TOKEN if you add Stripe later).
"""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from tracks import TRACKS, get_track

load_dotenv()

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

# Optional: Stripe secret for future checkout code (not used in this minimal bot).
_stripe = os.getenv("STRIPE_TOKEN", "").strip()


def _buy_keyboard(track: dict) -> InlineKeyboardMarkup:
    """Кнопки для детального экрана трека."""
    url = (track.get("buy_url") or "").strip()
    buy_button = (
        InlineKeyboardButton("💳 Buy Now", url=url)
        if url.startswith(("http://", "https://"))
        else InlineKeyboardButton("💳 Buy Now", callback_data="buy_unavailable")
    )
    return InlineKeyboardMarkup(
        [
            [buy_button],
            [InlineKeyboardButton("🏠 Back to Catalog", callback_data="browse")],
        ]
    )


def _detail_text(track: dict) -> str:
    """Текст карточки трека в детальном просмотре."""
    esc = html.escape
    return (
        f"✨ {esc(track['title'])}\n\n"
        f"{esc(track['description'])}\n\n"
        f"💰 Price: {esc(track['price'])}"
    )


def _catalog_keyboard() -> InlineKeyboardMarkup:
    """Собираем каталог 16 треков в 2 колонки."""
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(TRACKS), 2):
        left = TRACKS[i]
        row = [InlineKeyboardButton(left["short_title"], callback_data=str(left["id"]))]
        if i + 1 < len(TRACKS):
            right = TRACKS[i + 1]
            row.append(InlineKeyboardButton(right["short_title"], callback_data=str(right["id"])))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def _send_catalog_view(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показываем витрину: сначала альбом из 4 обложек, потом сетка кнопок 2x8."""
    try:
        first_four = TRACKS[:4]
        media_group: list[InputMediaPhoto] = []
        missing_titles: list[str] = []

        # Отправляем обложки треков одним альбомом, если файлы найдены.
        for track in first_four:
            cover_path = ROOT / track["cover"]
            if cover_path.is_file():
                with cover_path.open("rb") as photo:
                    media_group.append(
                        InputMediaPhoto(
                            media=photo.read(),
                            caption=f"🎵 {track['title']}\n💰 $16",
                        )
                    )
            else:
                missing_titles.append(track["title"])
                logger.warning("Cover not found for track %s: %s", track["id"], cover_path)

        if media_group:
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)

        # Если части обложек нет, показываем аккуратный fallback-текст.
        for title in missing_titles:
            await context.bot.send_message(chat_id=chat_id, text=f"🎵 {title}")

        await context.bot.send_message(
            chat_id=chat_id,
            text="Choose a track:",
            reply_markup=_catalog_keyboard(),
        )
    except Exception:
        logger.exception("Failed to send catalog view")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Something went wrong while loading the catalog. Please try again.",
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "Welcome! Tap the button to browse music.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎵 Browse Music", callback_data="browse")]]
        ),
    )


async def on_track_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    logger.info("Callback clicked: %s", query.data)
    chat = query.message.chat if query.message else None
    if chat is None:
        return

    if query.data == "browse":
        await _send_catalog_view(chat.id, context)
        return

    if query.data == "buy_unavailable":
        await context.bot.send_message(
            chat_id=chat.id,
            text="Payment link is not set yet. Please contact support.",
        )
        return

    if not query.data.isdigit():
        return

    try:
        tid = int(query.data)
        track = get_track(tid)
        if track is None:
            await context.bot.send_message(chat_id=chat.id, text="Unknown track.")
            return

        cover_path = ROOT / track["cover"]
        if cover_path.is_file():
            with cover_path.open("rb") as photo:
                await context.bot.send_photo(chat_id=chat.id, photo=photo)
        else:
            logger.warning("Cover missing in detail view for track %s: %s", tid, cover_path)
            await context.bot.send_message(chat_id=chat.id, text=f"🎵 {track['title']}")

        await context.bot.send_message(
            chat_id=chat.id,
            text=_detail_text(track),
            parse_mode="HTML",
            reply_markup=_buy_keyboard(track),
        )
    except Exception:
        logger.exception("Failed to process track callback: %s", query.data)
        await context.bot.send_message(
            chat_id=chat.id,
            text="Something went wrong while opening this track. Please try again.",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if err is not None:
        logger.error("Update caused error", exc_info=err)
    else:
        logger.error("Update caused error (no context.error)")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN in .env (see comments in .env file).")

    if _stripe:
        logger.info("STRIPE_TOKEN is set (ready if you add payment code).")
    else:
        logger.info("STRIPE_TOKEN not set — only needed when you connect Stripe.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_track_button, pattern=r"^(browse|buy_unavailable|\d+)$"))
    app.add_error_handler(error_handler)
    logger.info("Bot polling…")
    app.run_polling()


if __name__ == "__main__":
    main()
