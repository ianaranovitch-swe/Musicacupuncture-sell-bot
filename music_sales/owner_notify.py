"""Уведомления владельцу и разработчику бота о ключевых действиях пользователей."""

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


def owner_and_developer_chat_ids(*, skip_telegram_user_id: int | None = None) -> list[int]:
    """
    Кому слать служебные уведомления: OWNER_TELEGRAM_ID и DEVELOPER_TELEGRAM_ID (без дублей).
    Не шлём человеку, который сам вызвал событие (например владелец нажал /start).
    """
    out: list[int] = []
    for cid in (config.owner_telegram_id_int(), config.developer_telegram_id_int()):
        if cid is None:
            continue
        if skip_telegram_user_id is not None and cid == skip_telegram_user_id:
            continue
        if cid not in out:
            out.append(cid)
    return out


def _format_notify_lines(
    *,
    actor_label: str,
    event: str,
    song_name: str | None = None,
    payment_ok: bool | None = None,
    reason: str | None = None,
) -> list[str]:
    lines = [f"🛎 <b>{html.escape(event)}</b>", f"User: {html.escape(actor_label)}"]
    if song_name:
        lines.append(f"Track: {html.escape(song_name)}")
    if payment_ok is True:
        lines.append("Payment: ✅ success")
    elif payment_ok is False:
        lines.append("Payment: ❌ failed")
    if reason:
        lines.append(f"Reason: {html.escape(reason)}")
    return lines


async def notify_owner_async(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    actor: Optional[User],
    event: str,
    song_name: str | None = None,
    payment_ok: bool | None = None,
    reason: str | None = None,
) -> None:
    """Асинхронно отправляет владельцу и разработчику короткое событие."""
    skip_id = actor.id if actor is not None else None
    text = "\n".join(
        _format_notify_lines(
            actor_label=_display_name(actor),
            event=event,
            song_name=song_name,
            payment_ok=payment_ok,
            reason=reason,
        )
    )
    for chat_id in owner_and_developer_chat_ids(skip_telegram_user_id=skip_id):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception:
            logger.exception("Failed to notify chat_id=%s asynchronously", chat_id)


def notify_owner_sync(
    bot: Bot,
    *,
    actor_name: str,
    event: str,
    song_name: str | None = None,
    payment_ok: bool | None = None,
    reason: str | None = None,
) -> None:
    """Синхронно отправляет владельцу и разработчику событие (Flask / webhook)."""
    text = "\n".join(
        _format_notify_lines(
            actor_label=actor_name,
            event=event,
            song_name=song_name,
            payment_ok=payment_ok,
            reason=reason,
        )
    )
    for chat_id in owner_and_developer_chat_ids():
        try:
            bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception:
            logger.exception("Failed to notify chat_id=%s synchronously", chat_id)
