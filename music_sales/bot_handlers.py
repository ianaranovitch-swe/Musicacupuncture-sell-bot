from __future__ import annotations

import asyncio
import html
import logging

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.catalog import discover_songs

logger = logging.getLogger(__name__)


def _format_visitor_notice(visitor: User) -> str:
    """Short HTML message for the bot owner."""
    uname = f"@{visitor.username}" if visitor.username else "(no username)"
    name = " ".join(x for x in (visitor.first_name, visitor.last_name or "") if x).strip() or "—"
    return (
        "🛎 <b>Someone opened the bot</b> (/start)\n\n"
        f"<b>User ID:</b> <code>{visitor.id}</code>\n"
        f"<b>Name:</b> {html.escape(name)}\n"
        f"<b>Username:</b> {html.escape(uname)}"
    )


async def notify_owner_about_visitor(context: ContextTypes.DEFAULT_TYPE, visitor: User) -> None:
    """Send the owner a private message when a user starts the bot."""
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


def _keyboard_markup():
    songs = discover_songs()
    rows = [
        [InlineKeyboardButton(f"{s['name']} — {s['price_sek']} SEK", callback_data=k)]
        for k, s in sorted(songs.items(), key=lambda kv: kv[1]["name"].lower())
    ]
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user = update.effective_user
    if user is not None:
        logger.info("/start from user_id=%s username=%s", user.id, user.username or "-")
        await notify_owner_about_visitor(context, user)
    if not discover_songs():
        await update.message.reply_text(
            "No tracks available yet. Add audio files (.mp3, .wav, .m4a, …) to the "
            "SONGS folder on the server, then try again."
        )
        return
    await update.message.reply_text("Choose a track to buy:", reply_markup=_keyboard_markup())


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
