"""Платежи Telegram (провайдер Stripe): обработка pre_checkout_query и successful_payment."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.buy_constants import parse_invoice_payload
from music_sales.catalog import discover_songs, song_path

logger = logging.getLogger(__name__)


def _mp3_only_songs(all_songs: dict) -> dict:
    """Оставить только .mp3 (для /buy и проверок оплаты)."""
    out: dict = {}
    for song_id, meta in all_songs.items():
        file_path = str(meta.get("file", "")).lower()
        if file_path.endswith(".mp3"):
            out[song_id] = meta
    return out


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if query is None:
        return

    payload = query.invoice_payload or ""
    parsed = parse_invoice_payload(payload)
    if parsed is None:
        await query.answer(ok=False, error_message="Invalid payment data.")
        logger.warning("pre_checkout invalid payload: %r", payload)
        return

    song_id, user_id = parsed
    if query.from_user is None or query.from_user.id != user_id:
        await query.answer(ok=False, error_message="Payment does not match the user.")
        logger.warning("pre_checkout user mismatch: expected=%s got=%s", user_id, query.from_user.id if query.from_user else None)
        return

    songs = _mp3_only_songs(discover_songs())
    if song_id not in songs:
        await query.answer(ok=False, error_message="This track is no longer available.")
        logger.warning("pre_checkout unknown song_id=%s", song_id)
        return

    currency_expected = (config.PAYMENTS_CURRENCY or "USD").strip().upper()
    if query.currency != currency_expected:
        await query.answer(ok=False, error_message="Invalid invoice currency.")
        logger.warning("pre_checkout bad currency: got=%s expected=%s", query.currency, currency_expected)
        return

    song = songs[song_id]
    expected_minor = int(song["price_usd"]) * 100
    total = int(query.total_amount)
    if total != expected_minor:
        await query.answer(ok=False, error_message="Invalid amount.")
        logger.warning("pre_checkout bad amount: got=%s expected=%s song_id=%s", total, expected_minor, song_id)
        return

    path = song_path(song_id)
    if not path.is_file():
        await query.answer(ok=False, error_message="Track file is missing on the server.")
        logger.error("pre_checkout missing file: %s", path)
        return

    await query.answer(ok=True)
    logger.info("pre_checkout OK: user_id=%s song_id=%s amount=%s", user_id, song_id, total)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if msg is None or msg.successful_payment is None:
        return

    sp = msg.successful_payment
    payload = sp.invoice_payload or ""
    parsed = parse_invoice_payload(payload)
    if parsed is None:
        await msg.reply_text("Payment succeeded, but I couldn't determine which track it was. Please contact support.")
        logger.error("successful_payment invalid payload: %r", payload)
        return

    song_id, user_id = parsed
    if msg.from_user is None or msg.from_user.id != user_id:
        await msg.reply_text("Payment succeeded, but the payer doesn't match this chat user. Please contact support.")
        logger.error("successful_payment user mismatch: payload_user=%s from_user=%s", user_id, msg.from_user.id if msg.from_user else None)
        return

    songs = _mp3_only_songs(discover_songs())
    if song_id not in songs:
        await msg.reply_text("Payment succeeded, but this track is no longer available.")
        logger.error("successful_payment unknown song_id=%s", song_id)
        return

    path = song_path(song_id)
    if not path.is_file():
        await msg.reply_text("Payment succeeded, but the track file is missing on the server. Please contact support.")
        logger.error("successful_payment missing file: %s", path)
        return

    title = str(songs[song_id]["name"])
    try:
        with path.open("rb") as f:
            await msg.reply_audio(audio=f, title=title, filename=path.name)
    except OSError:
        logger.exception("successful_payment failed to read/send audio: %s", path)
        await msg.reply_text("Payment succeeded, but I couldn't send the file. Please contact support.")

    logger.info("successful_payment delivered: user_id=%s song_id=%s file=%s", user_id, song_id, path.name)
