from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import stripe
from flask import Flask, jsonify, request, send_from_directory
from telegram import Bot

from music_sales import config
from music_sales.catalog import discover_songs, project_root, resolve_song_id_by_audio_stem, unit_amount_for_song
from music_sales.owner_notify import notify_owner_sync

logger = logging.getLogger(__name__)
SUPPORTED_CHECKOUT_CURRENCIES = {"usd", "eur", "sek"}

# Не даём Stripe SDK засорять логи на уровне DEBUG (там могут быть чувствительные поля).
logging.getLogger("stripe").setLevel(logging.WARNING)


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


_bot_instance: Optional[Bot] = None


def _get_bot() -> Bot:
    """Return the cached Bot instance, creating it on first call.

    Using a lazy singleton means Gunicorn workers that never handle a webhook
    request will never instantiate a Bot, so they won't compete with the
    worker service's polling loop for the same Telegram token.
    """
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = Bot(token=config.BOT_TOKEN)
    return _bot_instance


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

    _injected_bot = bot

    if stripe_webhook_secret is not None:
        effective_wh_secret = stripe_webhook_secret
    else:
        effective_wh_secret = config.STRIPE_WEBHOOK_SECRET

    stripe.api_key = stripe_secret

    app = Flask(__name__)

    def root_path() -> Path:
        return project_root_override if project_root_override is not None else project_root()

    def _normalize_cors_origin(origin: str) -> str:
        """Сравниваем Origin без пробелов и хвостового / (частая опечатка в MINIAPP_CORS_ORIGINS)."""
        return (origin or "").strip().rstrip("/").lower()

    def _cors_origins_from_env() -> str:
        """Читаем при каждом запросе: на Railway env иногда важнее, чем значение при первом import."""
        return (os.environ.get("MINIAPP_CORS_ORIGINS") or config.MINIAPP_CORS_ORIGINS or "").strip()

    def _strip_fragment_quotes(fragment: str) -> str:
        """Убираем лишние кавычки вокруг origin из UI (Railway / .env)."""
        s = (fragment or "").strip()
        if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
            s = s[1:-1].strip()
        return s

    def _cors_headers_for_create_checkout() -> dict[str, str]:
        """CORS для Mini App на другом origin (например GitHub Pages)."""
        origin_raw = (request.headers.get("Origin") or "").strip()
        raw = _cors_origins_from_env()
        if not origin_raw or not raw:
            return {}
        origin_key = _normalize_cors_origin(origin_raw)
        allowed_keys = {
            _normalize_cors_origin(_strip_fragment_quotes(x)) for x in raw.split(",") if x.strip()
        }
        if origin_key not in allowed_keys:
            logger.warning(
                "CORS: checkout request Origin=%r not in MINIAPP_CORS_ORIGINS (normalized keys mismatch)",
                origin_raw[:160],
            )
            return {}
        # В заголовке ответа должно совпадать с тем, что прислал браузер (обычно без хвостового /).
        # «*» для Allow-Headers: без credentials браузеры (в т.ч. Telegram WebView) чаще проходят preflight.
        return {
            "Access-Control-Allow-Origin": origin_raw,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        }

    def _path_is_checkout_cors() -> bool:
        """Путь к checkout (иногда за прокси бывает префикс — проверяем и точное совпадение)."""
        p = (request.path or "").rstrip("/") or ""
        return p in ("/create-checkout", "/create-payment") or p.endswith(
            ("/create-checkout", "/create-payment")
        )

    @app.after_request
    def _cors_after_create_checkout(response):  # noqa: WPS430 — замыкание на Flask app
        if _path_is_checkout_cors():
            for k, v in _cors_headers_for_create_checkout().items():
                response.headers[k] = v
        return response

    def _checkout_unit_amount(song: Dict[str, Any], currency: str) -> int:
        """Для sek — фиксированная сумма в öre (из env); для usd/eur — из каталога."""
        if currency == "sek":
            try:
                return int((config.CHECKOUT_SEK_UNIT_AMOUNT or "16900").strip() or "16900")
            except ValueError:
                return 16900
        return unit_amount_for_song(song)

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

    @app.route("/create-checkout", methods=["OPTIONS"])
    @app.route("/create-payment", methods=["OPTIONS"])
    def create_checkout_options() -> Any:
        """Preflight для браузера (Mini App на другом домене)."""
        return "", 204

    @app.route("/create-checkout", methods=["POST"])
    @app.route("/create-payment", methods=["POST"])
    def create_checkout() -> Any:
        data = request.get_json(silent=True) or {}
        song_id = data.get("song_id")
        track_id = data.get("track_id")
        # Только для Mini App (track_id): опциональный секрет в заголовке. /buy шлёт только song_id — без секрета.
        sec = (config.MINIAPP_CHECKOUT_SECRET or "").strip()
        if track_id is not None and sec:
            if (request.headers.get("X-Miniapp-Checkout-Secret") or "").strip() != sec:
                return jsonify({"error": "Unauthorized"}), 401

        telegram_id = data.get("telegram_id")
        telegram_name = str(data.get("telegram_name") or "Unknown user")
        currency = str(data.get("currency") or "usd").strip().lower()

        # Mini App шлёт track_id 1..16 — сопоставляем с файлом в tracks.py и song_id каталога.
        if song_id is None and track_id is not None:
            try:
                from pathlib import Path as _Path

                from tracks import get_track as _get_track

                t = _get_track(int(track_id))
            except (ImportError, ValueError, TypeError, AttributeError):
                t = None
            if t:
                stem = _Path(str(t.get("audio", ""))).stem
                if stem:
                    song_id = resolve_song_id_by_audio_stem(stem)

        if song_id is None or telegram_id is None:
            return jsonify({"error": "song_id (or track_id) and telegram_id are required"}), 400
        if currency not in SUPPORTED_CHECKOUT_CURRENCIES:
            return jsonify({"error": "Unsupported currency"}), 400
        catalog = get_catalog()
        try:
            song = catalog[song_id]
        except KeyError:
            return jsonify({"error": "Unknown song_id"}), 400

        try:
            unit_amount = _checkout_unit_amount(song, currency)
            session = stripe.checkout.Session.create(
                automatic_payment_methods={"enabled": True},
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {"name": song["name"]},
                            "unit_amount": unit_amount,
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

        active_bot = _injected_bot or _get_bot()

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            telegram_id = session["metadata"]["telegram_id"]
            song_id = session["metadata"]["song_id"]
            telegram_name = str(session.get("metadata", {}).get("telegram_name") or "Unknown user")
            song_name = str(get_catalog().get(song_id, {}).get("name") or song_id)
            try:
                deliver_purchase(
                    active_bot,
                    int(telegram_id),
                    song_id,
                    get_catalog(),
                    root_path(),
                )
                notify_owner_sync(
                    active_bot,
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=True,
                )
            except OSError as e:
                logger.exception("Failed to send audio: %s", e)
                notify_owner_sync(
                    active_bot,
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=False,
                    reason="Audio delivery failed",
                )
            except KeyError:
                logger.exception("Unknown song in webhook metadata: %s", song_id)
                notify_owner_sync(
                    active_bot,
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
                active_bot,
                actor_name=telegram_name,
                event="Payment result",
                song_name=song_name,
                payment_ok=False,
                reason=event["type"],
            )

        return "", 200

    @app.route("/health")
    def health_json() -> Any:
        """JSON: файлы songs/covers, Stripe, backend, Mini App / CORS (без секретов)."""
        try:
            from music_sales.health_report import build_health_report

            return jsonify(build_health_report())
        except Exception as e:
            logger.exception("GET /health failed")
            return jsonify({"error": str(e)}), 500

    @app.route("/success")
    def success() -> str:
        return "Payment successful! You can return to Telegram."

    @app.route("/cancel")
    def cancel() -> str:
        return "Payment cancelled."

    return app
