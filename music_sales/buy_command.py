"""Команда /buy: показать список MP3, которые можно купить."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from music_sales.buy_constants import index_to_callback, sorted_buy_rows
from music_sales.catalog import discover_songs

logger = logging.getLogger(__name__)


def _mp3_only_songs(all_songs: dict) -> dict:
    """Оставить только .mp3 (так устроен сценарий /buy)."""
    out: dict = {}
    for song_id, meta in all_songs.items():
        file_path = str(meta.get("file", "")).lower()
        if file_path.endswith(".mp3"):
            out[song_id] = meta
    return out


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    songs = _mp3_only_songs(discover_songs())
    if not songs:
        await update.message.reply_text(
            "No MP3 tracks are available yet.\n"
            "Add `.mp3` files to the `songs/` folder on the server (or update `songs/catalog.json`). "
            "You can change the folder name with `AUDIO_SALES_DIR` in your environment (see `.env.example`)."
        )
        return

    rows = sorted_buy_rows(songs)
    keyboard = [
        [InlineKeyboardButton(f"{r.name} — ${r.price_usd}", callback_data=index_to_callback(idx))]
        for idx, r in enumerate(rows)
    ]

    await update.message.reply_text(
        "Choose a track to buy (MP3):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    logger.info("/buy catalog shown: tracks=%s user_id=%s", len(rows), update.effective_user.id if update.effective_user else "-")
