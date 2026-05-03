"""Уведомления владельцу бота о ключевых действиях пользователей."""

from __future__ import annotations

import html
import logging
from typing import Optional

from telegram import Bot, User
from telegram.ext import ContextTypes

from music_sales import config

logger = logging.getLogger(__name__)


def _display_name(user: Optional[User], fallback: str = "Unknown user") -> str:
    """Собирает понятное имя пользователя без показа Telegram ID."""
    if user is None:
        return fallback
    if user.username:
        return f"@{user.username}"
    full = " ".join(x for x in (user.first_name, user.last_name or "") if x).strip()
    return full or fallback


def _owner_chat_id(actor: Optional[User]) -> int | None:
    """Возвращает chat_id владельца, если валиден и не совпадает с самим владельцем."""
    owner_id = config.owner_telegram_id_int()
    if owner_id is None:
        return None
    if actor is not None and actor.id == owner_id:
        return None
    return owner_id


async def notify_owner_async(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    actor: Optional[User],
    event: str,
    song_name: str | None = None,
    payment_ok: bool | None = None,
    reason: str | None = None,
) -> None:
    """Асинхронно отправляет владельцу короткое событие по пользователю."""
    owner_id = _owner_chat_id(actor)
    if owner_id is None:
        return
    lines = [f"🛎 <b>{html.escape(event)}</b>", f"User: {html.escape(_display_name(actor))}"]
    if song_name:
        lines.append(f"Track: {html.escape(song_name)}")
    if payment_ok is True:
        lines.append("Payment: ✅ success")
    elif payment_ok is False:
        lines.append("Payment: ❌ failed")
    if reason:
        lines.append(f"Reason: {html.escape(reason)}")
    try:
        await context.bot.send_message(chat_id=owner_id, text="\n".join(lines), parse_mode="HTML")
    except Exception:
        logger.exception("Failed to notify owner asynchronously")


def notify_owner_sync(
    bot: Bot,
    *,
    actor_name: str,
    event: str,
    song_name: str | None = None,
    payment_ok: bool | None = None,
    reason: str | None = None,
) -> None:
    """Синхронно отправляет владельцу событие (используется во Flask webhook)."""
    owner_id = config.owner_telegram_id_int()
    if owner_id is None:
        return
    lines = [f"🛎 <b>{html.escape(event)}</b>", f"User: {html.escape(actor_name)}"]
    if song_name:
        lines.append(f"Track: {html.escape(song_name)}")
    if payment_ok is True:
        lines.append("Payment: ✅ success")
    elif payment_ok is False:
        lines.append("Payment: ❌ failed")
    if reason:
        lines.append(f"Reason: {html.escape(reason)}")
    try:
        bot.send_message(chat_id=owner_id, text="\n".join(lines), parse_mode="HTML")
    except Exception:
        logger.exception("Failed to notify owner synchronously")
