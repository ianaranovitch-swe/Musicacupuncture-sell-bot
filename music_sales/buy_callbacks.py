"""Callback'и для /buy: выбор трека и выбор способа оплаты."""

from __future__ import annotations

import asyncio
import logging

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.buy_constants import (
    PAY_CB_LINK,
    PAY_CB_TELEGRAM,
    UD_PENDING_SONG_ID,
    build_invoice_payload,
    parse_pay_method,
    parse_track_index,
    pay_method_callback,
    sorted_buy_rows,
)
from music_sales.catalog import discover_songs

logger = logging.getLogger(__name__)


def _mp3_only_songs(all_songs: dict) -> dict:
    out: dict = {}
    for song_id, meta in all_songs.items():
        file_path = str(meta.get("file", "")).lower()
        if file_path.endswith(".mp3"):
            out[song_id] = meta
    return out


async def buy_track_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    songs = _mp3_only_songs(discover_songs())
    rows = sorted_buy_rows(songs)
    idx = parse_track_index(query.data)
    if idx is None or idx < 0 or idx >= len(rows):
        if query.message:
            await query.message.reply_text("I didn't understand that track selection. Try again: /buy")
        logger.warning("Invalid /buy track callback: data=%s", query.data)
        return

    song_id = rows[idx].song_id
    context.user_data[UD_PENDING_SONG_ID] = song_id

    keyboard = [
        [
            InlineKeyboardButton("Pay inside Telegram (Stripe)", callback_data=pay_method_callback(PAY_CB_TELEGRAM)),
        ],
        [
            InlineKeyboardButton("Pay via external link", callback_data=pay_method_callback(PAY_CB_LINK)),
        ],
    ]

    meta = songs.get(song_id, {})
    title = str(meta.get("name", song_id))
    price = int(meta.get("price_usd", 0) or 0)

    text = (
        f"Track: <b>{title}</b>\n"
        f"Price: <b>${price} USD</b>\n\n"
        "Choose a payment method:"
    )

    if query.message:
        await query.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    logger.info("buy track selected: user_id=%s song_id=%s", query.from_user.id if query.from_user else "-", song_id)


async def buy_pay_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None or query.from_user is None:
        return

    await query.answer()

    method = parse_pay_method(query.data)
    if method not in (PAY_CB_TELEGRAM, PAY_CB_LINK):
        if query.message:
            await query.message.reply_text("I didn't understand that payment method. Try again: /buy")
        logger.warning("Invalid /buy pay callback: data=%s", query.data)
        return

    song_id = str(context.user_data.get(UD_PENDING_SONG_ID) or "")
    songs = _mp3_only_songs(discover_songs())
    if not song_id or song_id not in songs:
        if query.message:
            await query.message.reply_text("Pick a track first: /buy")
        logger.warning("Missing pending song for pay method: user_id=%s", query.from_user.id)
        return

    meta = songs[song_id]
    title = str(meta["name"])
    price_usd = int(meta["price_usd"])

    if method == PAY_CB_LINK:
        await _stripe_checkout_link(query, backend_url=config.BACKEND_URL, song_id=song_id, user_id=query.from_user.id)
        logger.info("buy external checkout: user_id=%s song_id=%s", query.from_user.id, song_id)
        return

    # Telegram Payments (провайдер Stripe)
    provider = (config.PAYMENTS_PROVIDER_TOKEN or "").strip()
    if not provider:
        if query.message:
            await query.message.reply_text(
                "In-Telegram payments are not configured: missing PAYMENTS_PROVIDER_TOKEN.\n"
                "Set it in your environment variables (see `.env.example`)."
            )
        logger.error("PAYMENTS_PROVIDER_TOKEN is missing; cannot sendInvoice")
        return

    currency = (config.PAYMENTS_CURRENCY or "USD").strip().upper()
    description = f"MP3: {title}"

    # Сумма в минимальных единицах валюты (для USD это центы: $1 = 100).
    # В PTB v22 `prices` должен быть sequence[LabeledPrice].
    prices = [LabeledPrice(title, int(price_usd * 100))]

    payload = build_invoice_payload(song_id=song_id, user_id=query.from_user.id)

    if query.message is None:
        logger.warning("callback_query.message is None for invoice")
        return

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title[:32],  # Telegram ограничивает длину title
        description=description[:255],
        payload=payload,
        currency=currency,
        prices=prices,
        provider_token=provider,
    )
    logger.info("buy telegram invoice sent: user_id=%s song_id=%s currency=%s", query.from_user.id, song_id, currency)


async def _stripe_checkout_link(query, *, backend_url: str, song_id: str, user_id: int) -> None:
    if query.message is None:
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
    except requests.RequestException:
        logger.exception("Checkout request failed for /buy external flow")
        payment_url = None
    except ValueError:
        logger.exception("Invalid JSON from backend for /buy external flow")
        payment_url = None

    if not payment_url:
        await query.message.reply_text("Could not create a checkout session right now. Please try again later.")
        return

    await query.message.reply_text(f"Pay here:\n{payment_url}")
