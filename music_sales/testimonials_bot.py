"""
Telegram: Customer Reviews (кнопки, листание, цитата в /start).
"""

from __future__ import annotations

import logging
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from music_sales.testimonials_store import (
    first_sentence,
    format_telegram_review,
    load_visible_testimonials,
)

logger = logging.getLogger(__name__)

REVIEWS_OPEN_CB = "reviews:open"
REVIEWS_PREV_CB = "reviews:prev"
REVIEWS_NEXT_CB = "reviews:next"
REVIEWS_BROWSE_CB = "reviews:browse"
REVIEWS_START_CB = "reviews:start_all"

UD_REVIEWS_INDEX = "reviews_index"


def _visible_reviews(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    items = load_visible_testimonials()
    if not items:
        return []
    items = sorted(items, key=lambda x: int(x.get("id") or 0))
    return items


def _get_index(context: ContextTypes.DEFAULT_TYPE, total: int) -> int:
    if total <= 0:
        return 0
    idx = int(context.user_data.get(UD_REVIEWS_INDEX, 0) or 0)
    return max(0, min(idx, total - 1))


def _reviews_keyboard(*, show_browse: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("◀️ Previous", callback_data=REVIEWS_PREV_CB),
            InlineKeyboardButton("▶️ Next", callback_data=REVIEWS_NEXT_CB),
        ],
    ]
    if show_browse:
        rows.append([InlineKeyboardButton("🎵 Browse Music", callback_data=REVIEWS_BROWSE_CB)])
    return InlineKeyboardMarkup(rows)


def random_start_testimonial_blurb() -> tuple[str, InlineKeyboardMarkup | None]:
    """Короткая цитата для /start и кнопка «Read all reviews»."""
    items = load_visible_testimonials()
    if not items:
        return "", None
    item = random.choice(items)
    quote = first_sentence(str(item.get("text") or ""))
    name = str(item.get("name") or "").strip()
    city = str(item.get("city") or "").strip()
    lines = [
        "⭐ What our customers say:",
        f"'{quote}'",
        f"— {name}, {city}",
    ]
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⭐ Read all reviews", callback_data=REVIEWS_START_CB)]]
    )
    return "\n".join(lines), markup


def main_menu_reviews_button_row() -> list[InlineKeyboardButton]:
    """Кнопка в главном меню (/start подарок)."""
    return [InlineKeyboardButton("⭐ Customer Reviews", callback_data=REVIEWS_OPEN_CB)]


async def _send_review_at_index(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit_message_id: int | None = None,
) -> None:
    items = _visible_reviews(context)
    if not items:
        text = "Customer reviews are not available yet. Please check back soon."
        if edit_message_id is not None:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=edit_message_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)
        return

    total = len(items)
    idx = _get_index(context, total)
    context.user_data[UD_REVIEWS_INDEX] = idx
    body = format_telegram_review(items[idx], index=idx + 1, total=total)
    markup = _reviews_keyboard()

    if edit_message_id is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=body,
                reply_markup=markup,
            )
            return
        except Exception:
            logger.debug("edit_message_text failed, sending new message", exc_info=True)

    await context.bot.send_message(chat_id=chat_id, text=body, reply_markup=markup)


async def reviews_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Листание отзывов и переход в магазин."""
    q = update.callback_query
    if q is None or q.data is None:
        return
    await q.answer()
    chat_id = q.message.chat_id if q.message else None
    if chat_id is None:
        return

    items = _visible_reviews(context)
    total = len(items)
    idx = _get_index(context, total)

    if q.data == REVIEWS_PREV_CB and total:
        context.user_data[UD_REVIEWS_INDEX] = (idx - 1) % total
    elif q.data == REVIEWS_NEXT_CB and total:
        context.user_data[UD_REVIEWS_INDEX] = (idx + 1) % total
    elif q.data in (REVIEWS_OPEN_CB, REVIEWS_START_CB):
        context.user_data[UD_REVIEWS_INDEX] = 0

    if q.data == REVIEWS_BROWSE_CB:
        from music_sales.bot_handlers import _send_miniapp_store_opener_if_configured

        await _send_miniapp_store_opener_if_configured(update, context)
        if q.message:
            await q.message.reply_text("Open the Music Store from the button above to browse all tracks.")
        return

    msg_id = q.message.message_id if q.message else None
    await _send_review_at_index(chat_id, context, edit_message_id=msg_id)
