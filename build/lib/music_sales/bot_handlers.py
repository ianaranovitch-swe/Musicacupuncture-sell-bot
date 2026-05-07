from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User, WebAppInfo
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.owner_notify import notify_owner_async

logger = logging.getLogger(__name__)


async def notify_owner_about_visitor(context: ContextTypes.DEFAULT_TYPE, visitor: User) -> None:
    """Отправить владельцу событие о запуске бота без показа ID пользователя."""
    await notify_owner_async(
        context,
        actor=visitor,
        event="Bot started",
    )


def _miniapp_store_row() -> list[InlineKeyboardButton] | None:
    """Одна строка с Mini App, если задан валидный HTTPS URL (требование Telegram)."""
    url = config.resolved_miniapp_url()
    if not url.startswith("https://"):
        return None
    return [InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=url))]


async def _send_miniapp_store_opener_if_configured(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Первое сообщение при /start: кнопка WebApp (тексты UI на английском)."""
    if update.message is None:
        return
    row = _miniapp_store_row()
    if not row:
        return
    welcome = "Welcome! Tap the button below to open the Music Store."
    if config.test_mode_active():
        welcome = "[TEST] " + welcome
    await update.message.reply_text(
        welcome,
        reply_markup=InlineKeyboardMarkup([row]),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    # Новый UX: на /start показываем только вход в Mini App.
    await _send_miniapp_store_opener_if_configured(update, context)
    user = update.effective_user
    if user is not None:
        logger.info("/start from user_id=%s username=%s", user.id, user.username or "-")
        await notify_owner_about_visitor(context, user)
    if not _miniapp_store_row():
        await update.message.reply_text(
            "Music Store is not configured yet. Ask admin to set MINIAPP_URL (HTTPS) and BACKEND_URL."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Краткая справка: у бота остался только Mini App сценарий."""
    if update.message is None:
        return

    lines = [
        "This bot sells MP3 tracks via the Mini App and sends paid audio in Telegram.",
        "",
        "Commands:",
        "• /start — open the Music Store Mini App",
        "• /help — show this help message",
        "• /health — owner/developer diagnostics only",
        "",
        "How to buy:",
        "1) Open /start",
        "2) Choose a track and currency in the Mini App",
        "3) Tap Buy and complete Stripe checkout",
        "",
        "Tip: if checkout opened in background, tap Buy again and open the latest checkout link/button.",
    ]
    await update.message.reply_text("\n".join(lines))
