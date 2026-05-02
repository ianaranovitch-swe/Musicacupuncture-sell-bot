"""
Simple Telegram bot: list 16 tracks from tracks.py, show cover + text, buy link when set.

Run:  python bot.py

Needs in .env: BOT_TOKEN (and STRIPE_TOKEN if you add Stripe later).
Optional: MINIAPP_URL=https://.../miniapp.html (HTTPS) for the Music Store WebApp button.
"""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from tracks import TRACKS, get_track

load_dotenv()

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def _miniapp_url() -> str:
    """HTTPS URL страницы Mini App: MINIAPP_URL или {DOMAIN}/miniapp.html."""
    direct = (os.getenv("MINIAPP_URL") or "").strip()
    if direct.startswith("https://"):
        return direct
    base = (os.getenv("DOMAIN") or "").strip().rstrip("/")
    if base.startswith("https://"):
        return f"{base}/miniapp.html"
    return ""

# Optional: Stripe secret for future checkout code (not used in this minimal bot).
_stripe = os.getenv("STRIPE_TOKEN", "").strip()


def _buy_keyboard(track: dict) -> InlineKeyboardButton:
    """Кнопка оплаты для текущего трека."""
    url = (track.get("buy_url") or "").strip()
    return (
        InlineKeyboardButton("💳 Buy Now", url=url)
        if url.startswith(("http://", "https://"))
        else InlineKeyboardButton("💳 Buy Now", callback_data="buy_unavailable")
    )


def _detail_text(track: dict) -> str:
    """Текст карточки трека в детальном просмотре."""
    esc = html.escape
    return (
        f"✨ {esc(track['title'])}\n\n"
        f"{esc(track['description'])}\n\n"
        f"💰 Price: {esc(track['price'])}"
    )


def _next_track_id(track_id: int) -> int:
    """Следующий трек по кругу (после 16 снова 1)."""
    return 1 if track_id >= len(TRACKS) else track_id + 1


def _track_card_keyboard(track: dict) -> InlineKeyboardMarkup:
    """Полная клавиатура: опционально Mini App + 16 кнопок треков + Buy + NEXT."""
    rows: list[list[InlineKeyboardButton]] = []
    store_url = _miniapp_url()
    if store_url:
        rows.append([InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=store_url))])
    for i in range(0, len(TRACKS), 2):
        left = TRACKS[i]
        row = [InlineKeyboardButton(left["short_title"], callback_data=str(left["id"]))]
        if i + 1 < len(TRACKS):
            right = TRACKS[i + 1]
            row.append(InlineKeyboardButton(right["short_title"], callback_data=str(right["id"])))
        rows.append(row)
    rows.append([_buy_keyboard(track)])
    rows.append([InlineKeyboardButton("NEXT", callback_data=f"next:{_next_track_id(track['id'])}")])
    return InlineKeyboardMarkup(rows)


async def _send_track_card(chat_id: int, track: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показываем одну карточку трека сверху с обложкой/описанием и общей клавиатурой."""
    try:
        cover_path = ROOT / track["cover"]
        text = _detail_text(track)
        markup = _track_card_keyboard(track)
        if cover_path.is_file():
            with cover_path.open("rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
        else:
            logger.warning("Cover not found for track %s: %s", track["id"], cover_path)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎵 {track['title']}\n\n{text}",
                parse_mode="HTML",
                reply_markup=markup,
            )
    except Exception:
        logger.exception("Failed to send track card for track_id=%s", track.get("id"))
        await context.bot.send_message(
            chat_id=chat_id,
            text="Something went wrong while loading the track. Please try again.",
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    # Первое сообщение в чате: только WebApp — пользователь сразу открывает витрину.
    store_url = _miniapp_url()
    if store_url:
        await update.message.reply_text(
            "Welcome! Tap the button below to open the Music Store.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=store_url))]]
            ),
        )
    first_track = get_track(1)
    if first_track is None:
        await update.message.reply_text("No tracks available.")
        return
    await _send_track_card(update.message.chat.id, first_track, context)


async def on_track_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    logger.info("Callback clicked: %s", query.data)
    chat = query.message.chat if query.message else None
    if chat is None:
        return

    if query.data == "buy_unavailable":
        await context.bot.send_message(
            chat_id=chat.id,
            text="Payment link is not set yet. Please contact support.",
        )
        return

    try:
        if query.data.startswith("next:"):
            tid = int(query.data.split(":", 1)[1])
        elif query.data.isdigit():
            tid = int(query.data)
        else:
            return
        track = get_track(tid)
        if track is None:
            await context.bot.send_message(chat_id=chat.id, text="Unknown track.")
            return
        # Удаляем прошлую карточку, чтобы сверху всегда оставалась только одна актуальная.
        if query.message is not None:
            try:
                await query.message.delete()
            except Exception:
                logger.warning("Could not delete previous track card message")
        await _send_track_card(chat.id, track, context)
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
    app.add_handler(CallbackQueryHandler(on_track_button, pattern=r"^(buy_unavailable|\d+|next:\d+)$"))
    app.add_error_handler(error_handler)
    logger.info("Bot polling…")
    app.run_polling()


if __name__ == "__main__":
    main()
