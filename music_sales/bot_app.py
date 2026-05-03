from __future__ import annotations

import logging
from functools import partial

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from music_sales import config
from music_sales.bot_handlers import button, gallery_callback, start
from music_sales.buy_callbacks import buy_pay_method, buy_track_select
from music_sales.buy_command import buy
from music_sales.buy_payments import pre_checkout, successful_payment
from music_sales.health_report import cmd_health
from music_sales.logging_setup import setup_logging

logger = logging.getLogger(__name__)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if err is not None:
        logger.error("Unhandled exception in update handler", exc_info=err)
    else:
        logger.error("Unhandled error in update handler (no context.error)")


def build_application():
    if not config.BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. Set the environment variable BOT_TOKEN (see .env.example)."
        )
    application = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("health", cmd_health))

    # /buy: отдельные префиксы callback_data, чтобы не пересекаться с callback'ами /start
    application.add_handler(CallbackQueryHandler(buy_track_select, pattern=r"^b:t:\d{3}$"))
    application.add_handler(CallbackQueryHandler(buy_pay_method, pattern=r"^b:p:(tg|lk)$"))
    application.add_handler(CallbackQueryHandler(gallery_callback, pattern=r"^(g:s:\d{3}|g:n:\d{3})$"))

    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    application.add_handler(
        CallbackQueryHandler(partial(button, backend_url=config.BACKEND_URL))
    )
    application.add_error_handler(_error_handler)
    return application


def main() -> None:
    setup_logging()
    logger.info("Starting Telegram bot (polling)")
    try:
        build_application().run_polling()
    except Exception:
        logger.exception("Bot stopped due to an error (see traceback below)")
        raise
    finally:
        logger.info("Bot stopped")
