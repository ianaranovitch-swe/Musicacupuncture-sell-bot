from __future__ import annotations

import logging
from functools import partial

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from music_sales import config
from music_sales.bot_handlers import button, start
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
    finally:
        logger.info("Bot stopped")
