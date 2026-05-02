from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import stripe
from flask import Flask, jsonify, request, send_from_directory
from telegram import Bot

from music_sales import config
from music_sales.catalog import discover_songs, project_root, unit_amount_for_song
from music_sales.owner_notify import notify_owner_sync

logger = logging.getLogger(__name__)
SUPPORTED_CHECKOUT_CURRENCIES = {"usd", "eur", "sek"}


def deliver_purchase(
    bot: Bot,
    telegram_id: int,
    song_id: str,
    songs_catalog: Dict[str, Dict[str, Any]],
    root: Path,
) -> None:
    song = songs_catalog[song_id]
    path = root / song["file"]
    with open(path, "rb") as audio:
        bot.send_audio(chat_id=telegram_id, audio=audio, title=song["name"])


def _parse_webhook_event(
    stripe_webhook_secret: str,
) -> Union[stripe.Event, Tuple[Any, int]]:
    """
    Если задан `stripe_webhook_secret`, проверяем подпись Stripe-Signature (прод).

    Иначе парсим JSON из тела запроса (только локально/в тестах — нельзя открывать в интернет).
    """
    if stripe_webhook_secret:
        payload = request.get_data()
        sig_header = request.headers.get("Stripe-Signature")
        if not sig_header:
            return jsonify({"error": "Missing Stripe-Signature header"}), 400
        try:
            return stripe.Webhook.construct_event(payload, sig_header, stripe_webhook_secret)
        except ValueError as e:
            logger.warning("Invalid webhook payload: %s", e)
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError as e:
            logger.warning("Webhook signature verification failed: %s", e)
            return jsonify({"error": "Invalid signature"}), 400

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Expected JSON body"}), 400
    return stripe.Event.construct_from(body, stripe.api_key)


def create_app(
    bot: Optional[Bot] = None,
    songs_catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    stripe_secret: Optional[str] = None,
    domain: Optional[str] = None,
    project_root_override: Optional[Path] = None,
    stripe_webhook_secret: Optional[str] = None,
) -> Flask:
    """
    Параметр `stripe_webhook_secret`:
      - None: взять `STRIPE_WEBHOOK_SECRET` из окружения (рекомендуется в проде)
      - \"\": отключить проверку подписи (только тесты/локально)
    """
    stripe_secret = stripe_secret or config.STRIPE_SECRET_KEY

    def get_catalog() -> Dict[str, Dict[str, Any]]:
        return songs_catalog if songs_catalog is not None else discover_songs()
    domain = domain or config.DOMAIN
    if bot is None and not config.BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. The server needs it to send purchased audio in Telegram."
        )
    bot = bot or Bot(token=config.BOT_TOKEN)

    if stripe_webhook_secret is not None:
        effective_wh_secret = stripe_webhook_secret
    else:
        effective_wh_secret = config.STRIPE_WEBHOOK_SECRET

    stripe.api_key = stripe_secret

    app = Flask(__name__)

    def root_path() -> Path:
        return project_root_override if project_root_override is not None else project_root()

    @app.route("/miniapp.html")
    def miniapp_page() -> Any:
        """Статическая страница Telegram Mini App (один HTML-файл в корне репозитория)."""
        return send_from_directory(str(root_path()), "miniapp.html", mimetype="text/html")

    @app.route("/covers/<path:filename>")
    def miniapp_cover(filename: str) -> Any:
        """Обложки для Mini App: только файлы внутри папки covers (без выхода вверх по путям)."""
        covers_dir = (root_path() / "covers").resolve()
        try:
            target = (covers_dir / filename).resolve()
        except OSError:
            return jsonify({"error": "Invalid path"}), 400
        try:
            target.relative_to(covers_dir)
        except ValueError:
            return jsonify({"error": "Invalid path"}), 400
        if not target.is_file():
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(str(covers_dir), filename)

    @app.route("/create-checkout", methods=["POST"])
    def create_checkout() -> Any:
        data = request.get_json(silent=True) or {}
        song_id = data.get("song_id")
        telegram_id = data.get("telegram_id")
        telegram_name = str(data.get("telegram_name") or "Unknown user")
        currency = str(data.get("currency") or "usd").strip().lower()
        if song_id is None or telegram_id is None:
            return jsonify({"error": "song_id and telegram_id are required"}), 400
        if currency not in SUPPORTED_CHECKOUT_CURRENCIES:
            return jsonify({"error": "Unsupported currency"}), 400
        catalog = get_catalog()
        try:
            song = catalog[song_id]
        except KeyError:
            return jsonify({"error": "Unknown song_id"}), 400

        try:
            # Цена хранится как фиксированное число "16" в каталоге.
            # Сейчас используем это число как номинал для выбранной валюты.
            # При необходимости можно добавить отдельные цены по валютам.
            session = stripe.checkout.Session.create(
                automatic_payment_methods={"enabled": True},
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {"name": song["name"]},
                            "unit_amount": unit_amount_for_song(song),
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=domain + "/success",
                cancel_url=domain + "/cancel",
                metadata={
                    "telegram_id": str(telegram_id),
                    "telegram_name": telegram_name[:120],
                    "song_id": song_id,
                },
            )
        except stripe.error.StripeError as e:
            logger.exception("Stripe checkout failed: %s", e)
            return jsonify({"error": "Payment provider error"}), 502

        return jsonify({"url": session.url})

    @app.route("/webhook", methods=["POST"])
    def webhook() -> Any:
        parsed = _parse_webhook_event(effective_wh_secret)
        if isinstance(parsed, tuple):
            return parsed
        event = parsed

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            telegram_id = session["metadata"]["telegram_id"]
            song_id = session["metadata"]["song_id"]
            telegram_name = str(session.get("metadata", {}).get("telegram_name") or "Unknown user")
            song_name = str(get_catalog().get(song_id, {}).get("name") or song_id)
            try:
                deliver_purchase(
                    bot,
                    int(telegram_id),
                    song_id,
                    get_catalog(),
                    root_path(),
                )
                notify_owner_sync(
                    bot,
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=True,
                )
            except OSError as e:
                logger.exception("Failed to send audio: %s", e)
                notify_owner_sync(
                    bot,
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=False,
                    reason="Audio delivery failed",
                )
            except KeyError:
                logger.exception("Unknown song in webhook metadata: %s", song_id)
                notify_owner_sync(
                    bot,
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_id,
                    payment_ok=False,
                    reason="Unknown song in metadata",
                )

        if event["type"] in ("checkout.session.expired", "checkout.session.async_payment_failed"):
            session = event["data"]["object"]
            meta = session.get("metadata", {}) if isinstance(session, dict) else {}
            song_id = str(meta.get("song_id") or "unknown")
            song_name = str(get_catalog().get(song_id, {}).get("name") or song_id)
            telegram_name = str(meta.get("telegram_name") or "Unknown user")
            notify_owner_sync(
                bot,
                actor_name=telegram_name,
                event="Payment result",
                song_name=song_name,
                payment_ok=False,
                reason=event["type"],
            )

        return "", 200

    @app.route("/success")
    def success() -> str:
        return "Payment successful! You can return to Telegram."

    @app.route("/cancel")
    def cancel() -> str:
        return "Payment cancelled."

    return app
