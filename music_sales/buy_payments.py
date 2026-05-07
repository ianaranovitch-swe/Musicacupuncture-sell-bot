"""Платежи Telegram (провайдер Stripe): обработка pre_checkout_query и successful_payment."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.buy_constants import parse_invoice_payload
from music_sales.catalog import discover_songs
from music_sales.file_id_delivery import PURCHASE_DELIVERY_CAPTION, file_id_for_song, load_file_ids_dict
from music_sales.owner_notify import notify_owner_async

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
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Payment attempt",
            payment_ok=False,
            reason="Invalid payload",
        )
        return

    song_id, user_id = parsed
    if query.from_user is None or query.from_user.id != user_id:
        await query.answer(ok=False, error_message="Payment does not match the user.")
        logger.warning("pre_checkout user mismatch: expected=%s got=%s", user_id, query.from_user.id if query.from_user else None)
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Payment attempt",
            payment_ok=False,
            reason="User mismatch",
        )
        return

    songs = _mp3_only_songs(discover_songs())
    if song_id not in songs:
        await query.answer(ok=False, error_message="This track is no longer available.")
        logger.warning("pre_checkout unknown song_id=%s", song_id)
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Payment attempt",
            song_name=song_id,
            payment_ok=False,
            reason="Unknown track",
        )
        return

    currency_expected = (config.PAYMENTS_CURRENCY or "USD").strip().upper()
    if query.currency != currency_expected:
        await query.answer(ok=False, error_message="Invalid invoice currency.")
        logger.warning("pre_checkout bad currency: got=%s expected=%s", query.currency, currency_expected)
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Payment attempt",
            song_name=song_id,
            payment_ok=False,
            reason="Currency mismatch",
        )
        return

    song = songs[song_id]
    expected_minor = int(song["price_usd"]) * 100
    total = int(query.total_amount)
    if total != expected_minor:
        await query.answer(ok=False, error_message="Invalid amount.")
        logger.warning("pre_checkout bad amount: got=%s expected=%s song_id=%s", total, expected_minor, song_id)
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Payment attempt",
            song_name=song_id,
            payment_ok=False,
            reason="Amount mismatch",
        )
        return

    # Доставка только по FILE_IDS_JSON (без MP3 на диске Railway).
    fid = file_id_for_song(song, load_file_ids_dict())
    if not fid:
        await query.answer(ok=False, error_message="Track is not available for delivery right now.")
        logger.error("pre_checkout missing FILE_IDS_JSON entry for song_id=%s", song_id)
        await notify_owner_async(
            context,
            actor=query.from_user,
            event="Payment attempt",
            song_name=song_id,
            payment_ok=False,
            reason="Missing Telegram file_id (FILE_IDS_JSON)",
        )
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
        await notify_owner_async(
            context,
            actor=msg.from_user,
            event="Payment result",
            payment_ok=False,
            reason="Invalid successful payload",
        )
        return

    song_id, user_id = parsed
    if msg.from_user is None or msg.from_user.id != user_id:
        await msg.reply_text("Payment succeeded, but the payer doesn't match this chat user. Please contact support.")
        logger.error("successful_payment user mismatch: payload_user=%s from_user=%s", user_id, msg.from_user.id if msg.from_user else None)
        await notify_owner_async(
            context,
            actor=msg.from_user,
            event="Payment result",
            payment_ok=False,
            reason="Payer mismatch",
        )
        return

    songs = _mp3_only_songs(discover_songs())
    if song_id not in songs:
        await msg.reply_text("Payment succeeded, but this track is no longer available.")
        logger.error("successful_payment unknown song_id=%s", song_id)
        await notify_owner_async(
            context,
            actor=msg.from_user,
            event="Payment result",
            song_name=song_id,
            payment_ok=False,
            reason="Unknown track after payment",
        )
        return

    song_meta = songs[song_id]
    fid = file_id_for_song(song_meta, load_file_ids_dict())
    if not fid:
        await msg.reply_text(
            "Sorry, there was an error delivering your file. Please contact support."
        )
        logger.error("successful_payment missing FILE_IDS_JSON for song_id=%s", song_id)
        await notify_owner_async(
            context,
            actor=msg.from_user,
            event="Payment result",
            song_name=song_id,
            payment_ok=False,
            reason="Missing Telegram file_id after payment",
        )
        return

    title = str(song_meta["name"])
    # Тот же file_id, что после upload_songs.py (send_document) — шлём документом.
    try:
        await msg.reply_document(document=fid, caption=PURCHASE_DELIVERY_CAPTION)
    except Exception:
        logger.exception("successful_payment failed to send document by file_id song_id=%s", song_id)
        await msg.reply_text(
            "Sorry, there was an error delivering your file. Please contact support."
        )
        await notify_owner_async(
            context,
            actor=msg.from_user,
            event="Payment result",
            song_name=title,
            payment_ok=False,
            reason="Document send by file_id failed",
        )
        return

    logger.info("successful_payment delivered: user_id=%s song_id=%s (file_id)", user_id, song_id)
    await notify_owner_async(
        context,
        actor=msg.from_user,
        event="Payment result",
        song_name=title,
        payment_ok=True,
    )
