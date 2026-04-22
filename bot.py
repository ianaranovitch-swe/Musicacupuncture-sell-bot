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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from tracks import TRACKS, get_track

load_dotenv()

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

# Optional: Stripe secret for future checkout code (not used in this minimal bot).
_stripe = os.getenv("STRIPE_TOKEN", "").strip()


def _button_label(track: dict, max_len: int = 64) -> str:
    """Telegram inline button text max 64 chars."""
    prefix = f"{track['id']}. "
    rest = max_len - len(prefix)
    title = track["title"]
    if len(title) <= rest:
        return prefix + title
    if rest <= 1:
        return prefix[:max_len]
    return prefix + title[: rest - 1] + "…"


def _buy_keyboard(track: dict) -> InlineKeyboardMarkup | None:
    url = (track.get("buy_url") or "").strip()
    if url.startswith(("http://", "https://")):
        return InlineKeyboardMarkup([[InlineKeyboardButton("Buy", url=url)]])
    return None


def _caption(track: dict) -> str:
    esc = html.escape
    lines = [
        f"<b>{esc(track['title'])}</b>",
        "",
        esc(track["description"]).replace("\n", "\n"),
        "",
        f"<b>{esc(track['price'])}</b>",
    ]
    if not (track.get("buy_url") or "").strip().startswith(("http://", "https://")):
        lines += ["", "<i>Buy link not set yet — replace PLACEHOLDER_URL_* in tracks.py</i>"]
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    rows = [
        [InlineKeyboardButton(_button_label(t), callback_data=f"track:{t['id']}")]
        for t in TRACKS
    ]
    await update.message.reply_text(
        "Choose a track (16 items):",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def on_track_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    if not query.data.startswith("track:"):
        return
    try:
        tid = int(query.data.split(":", 1)[1])
    except ValueError:
        return
    track = get_track(tid)
    if track is None:
        if query.message:
            await query.message.reply_text("Unknown track.")
        return

    cover_path = ROOT / track["cover"]
    caption = _caption(track)
    kb = _buy_keyboard(track)
    chat = query.message.chat if query.message else None
    if chat is None:
        return

    if cover_path.is_file():
        with cover_path.open("rb") as photo:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
    else:
        await context.bot.send_message(
            chat_id=chat.id,
            text=caption,
            parse_mode="HTML",
            reply_markup=kb,
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
    app.add_handler(CallbackQueryHandler(on_track_button, pattern=r"^track:\d+$"))
    app.add_error_handler(error_handler)
    logger.info("Bot polling…")
    app.run_polling()


if __name__ == "__main__":
    main()
