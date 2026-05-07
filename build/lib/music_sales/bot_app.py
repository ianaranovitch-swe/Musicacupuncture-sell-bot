from __future__ import annotations

import logging
import os
import socket
import time
import requests
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from music_sales import config
from music_sales.bot_handlers import help_command, start
from music_sales.buy_payments import pre_checkout, successful_payment
from music_sales.health_report import cmd_health
from music_sales.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _log_worker_identity() -> None:
    """В Railway по одной строке видно: не крутятся ли два контейнера с одним токеном (разные PID/hostname)."""
    railway_bits = []
    for key in (
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_REPLICA_ID",
        "RAILWAY_DEPLOYMENT_ID",
    ):
        val = os.environ.get(key)
        if val:
            railway_bits.append(f"{key}={val}")
    extra = (" " + " ".join(railway_bits)) if railway_bits else ""
    logger.info(
        "Worker identity: pid=%s hostname=%s%s",
        os.getpid(),
        socket.gethostname(),
        extra,
    )


def _log_webhook_preflight(token: str) -> None:
    """
    Один HTTP-запрос до PTB: если webhook уже висит на боте, в логах это видно.
    Сама ошибка Conflict почти всегда = второй процесс с тем же BOT_TOKEN (другой деплой / реплика).
    """
    t = (token or "").strip()
    if not t:
        return
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{t}/getWebhookInfo",
            timeout=10,
        )
        data = r.json()
        if not data.get("ok"):
            logger.warning("Preflight getWebhookInfo: telegram ok=false %s", data)
            return
        result = data.get("result") or {}
        url = (result.get("url") or "").strip()
        pending = result.get("pending_update_count")
        logger.info(
            "Preflight getWebhookInfo: webhook_configured=%s pending_update_count=%s",
            bool(url),
            pending,
        )
        if url:
            logger.warning(
                "Telegram still has a webhook URL set. python-telegram-bot will call "
                "delete_webhook when polling starts. If you use webhooks elsewhere, stop that first."
            )
    except Exception as exc:
        logger.warning("Preflight getWebhookInfo failed (network?): %s", exc)


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
    return ApplicationBuilder().token(config.BOT_TOKEN)


def _register_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("health", cmd_health))

    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_error_handler(_error_handler)


def _delay_before_polling_if_configured() -> None:
    """
    На Railway при смене деплоя кратко живут два контейнера с одним BOT_TOKEN — оба держат getUpdates → Conflict.
    Пауза перед run_polling даёт старому контейнеру чаще успеть завершиться (см. BOT_POLLING_START_DELAY_SECONDS).
    """
    raw = (os.environ.get("BOT_POLLING_START_DELAY_SECONDS") or "").strip()
    if not raw:
        return
    try:
        sec = float(raw)
    except ValueError:
        logger.warning("Invalid BOT_POLLING_START_DELAY_SECONDS=%r, ignoring", raw)
        return
    if sec <= 0:
        return
    logger.info(
        "Sleeping %.1f s before run_polling (BOT_POLLING_START_DELAY_SECONDS; mitigates deploy overlap).",
        sec,
    )
    time.sleep(sec)


def main() -> None:
    setup_logging()
    logger.info("Starting Telegram bot (polling)")
    if config.test_mode_active():
        logger.warning(
            "TEST_MODE is ON — track prices follow TEST_PRICE_USD/SEK; web checkout uses reduced amounts."
        )
    _log_worker_identity()
    try:
        _log_webhook_preflight(config.BOT_TOKEN)
        application = build_application().build()
        _register_handlers(application)
        _delay_before_polling_if_configured()
        application.run_polling()
    except Exception:
        logger.exception("Bot stopped due to an error (see traceback below)")
        raise
    finally:
        logger.info("Bot stopped")
