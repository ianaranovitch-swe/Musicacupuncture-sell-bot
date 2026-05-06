from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
import stripe
from flask import Flask, jsonify, request, send_from_directory

from music_sales import config
from music_sales.catalog import discover_songs, project_root, resolve_song_id_by_audio_stem, unit_amount_for_song

logger = logging.getLogger(__name__)
SUPPORTED_CHECKOUT_CURRENCIES = {"usd", "eur", "sek"}

# Не даём Stripe SDK засорять логи на уровне DEBUG (там могут быть чувствительные поля).
logging.getLogger("stripe").setLevel(logging.WARNING)


def _tg_api_url(method: str) -> str:
    """Return the Telegram Bot API URL for the given method."""
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def deliver_purchase(
    telegram_id: int,
    song_id: str,
    songs_catalog: Dict[str, Dict[str, Any]],
    root: Path,
) -> None:
    song = songs_catalog[song_id]
    path = root / song["file"]
    with open(path, "rb") as audio:
        resp = requests.post(
            _tg_api_url("sendAudio"),
            data={"chat_id": telegram_id, "title": song["name"]},
            files={"audio": audio},
            timeout=60,
        )
        resp.raise_for_status()


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
    if not config.BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. The server needs it to send purchased audio in Telegram."
        )

    if stripe_webhook_secret is not None:
        effective_wh_secret = stripe_webhook_secret
    else:
        effective_wh_secret = config.STRIPE_WEBHOOK_SECRET

    stripe.api_key = stripe_secret

    app = Flask(__name__)

    def root_path() -> Path:
        return project_root_override if project_root_override is not None else project_root()

    def _cors_origins_from_env() -> str:
        """Читаем при каждом запросе: на Railway env иногда важнее, чем значение при первом import."""
        return (os.environ.get("MINIAPP_CORS_ORIGINS") or config.MINIAPP_CORS_ORIGINS or "").strip()

    def _strip_fragment_quotes(fragment: str) -> str:
        """Убираем лишние кавычки вокруг origin из UI (Railway / .env)."""
        s = (fragment or "").strip()
        if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
            s = s[1:-1].strip()
        return s

    def _cors_origin_key(value: str) -> Optional[str]:
        """
        Ключ для сравнения с заголовком Origin: scheme://host[:port] в нижнем регистре, без пути и без «/» в конце.

        Админы часто вставляют в MINIAPP_CORS_ORIGINS полный URL страницы
        (https://user.github.io/repo/miniapp.html) — браузер же шлёт только origin (https://user.github.io).
        Раньше сравнение ломалось; теперь парсим URL и берём только origin.
        """
        s = _strip_fragment_quotes((value or "").strip())
        s = s.lstrip("\ufeff").strip()
        if not s:
            return None
        if "://" not in s:
            s = f"https://{s}"
        try:
            p = urlparse(s)
        except Exception:
            return None
        if not p.scheme or not p.netloc:
            return None
        scheme = p.scheme.lower()
        host = (p.hostname or "").lower()
        if not host:
            return None
        port = p.port
        if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
            netloc = f"{host}:{port}"
        else:
            netloc = host
        return f"{scheme}://{netloc}"

    def _cors_headers_for_create_checkout() -> dict[str, str]:
        """CORS для Mini App на другом origin (например GitHub Pages)."""
        origin_raw = (request.headers.get("Origin") or "").strip()
        raw = _cors_origins_from_env()
        if not origin_raw or not raw:
            return {}
        origin_key = _cors_origin_key(origin_raw)
        if not origin_key:
            logger.warning("CORS: invalid Origin header %r", origin_raw[:160])
            return {}
        allowed_keys: set[str] = set()
        for part in raw.split(","):
            if not part.strip():
                continue
            k = _cors_origin_key(part)
            if k:
                allowed_keys.add(k)
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
        """Пути Mini App → backend: checkout, preflight и JSON цен (нужен тот же CORS)."""
        p = (request.path or "").rstrip("/") or ""
        tails = ("/create-checkout", "/create-payment", "/miniapp-pricing")
        return p in ("/create-checkout", "/create-payment", "/miniapp-pricing") or p.endswith(tails)

    @app.after_request
    def _cors_after_create_checkout(response):  # noqa: WPS430 — замыкание на Flask app
        if _path_is_checkout_cors():
            for k, v in _cors_headers_for_create_checkout().items():
                response.headers[k] = v
        return response

    def _checkout_unit_amount(song: Dict[str, Any], currency: str) -> int:
        """Для sek — фиксированная сумма в öre (из env); для usd/eur — из каталога. TEST_MODE — дешёвые суммы."""
        if config.test_mode_active():
            if currency == "sek":
                try:
                    sek_whole = int((os.environ.get("TEST_PRICE_SEK") or config.TEST_PRICE_SEK or "10").strip() or "10")
                    return max(100, sek_whole * 100)
                except ValueError:
                    return 1000
            try:
                minor = int(song.get("price_usd", 1) or 1) * 100
                return max(50, minor)
            except (TypeError, ValueError):
                return 100
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

    @app.route("/miniapp-pricing", methods=["GET", "OPTIONS"])
    def miniapp_pricing() -> Any:
        """
        JSON для Mini App: флаг теста и подписи цен (совпадают с Stripe Checkout на backend).
        GET с GitHub Pages — тот же CORS, что и у /create-payment.
        """
        if request.method == "OPTIONS":
            return "", 204
        if config.test_mode_active():
            try:
                usd_n = int((os.environ.get("TEST_PRICE_USD") or config.TEST_PRICE_USD or "1").strip() or "1")
            except ValueError:
                usd_n = 1
            try:
                sek_n = int((os.environ.get("TEST_PRICE_SEK") or config.TEST_PRICE_SEK or "10").strip() or "10")
            except ValueError:
                sek_n = 10
            usd_n = max(1, usd_n)
            sek_n = max(1, sek_n)
            return jsonify(
                {
                    "test_mode": True,
                    "usd_display": f"${usd_n}",
                    "sek_display": f"{sek_n} kr",
                    "badge_usd": f"USD · ${usd_n}",
                    "badge_sek": f"SEK · {sek_n} kr",
                }
            )
        try:
            usd_n = int((os.environ.get("DEFAULT_TRACK_PRICE_USD") or config.DEFAULT_TRACK_PRICE_USD or "16").strip() or "16")
        except ValueError:
            usd_n = 16
        try:
            ore = int((config.CHECKOUT_SEK_UNIT_AMOUNT or "16900").strip() or "16900")
        except ValueError:
            ore = 16900
        kr = max(1, ore // 100)
        return jsonify(
            {
                "test_mode": False,
                "usd_display": f"${usd_n}",
                "sek_display": f"{kr} kr",
                "badge_usd": f"USD · ${usd_n}",
                "badge_sek": f"SEK · {kr} kr",
            }
        )

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
            display_name = f"[TEST] {song['name']}" if config.test_mode_active() else song["name"]
            session = stripe.checkout.Session.create(
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {"name": display_name},
                            "unit_amount": unit_amount,
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=domain + "/success",
                cancel_url=domain + "/cancel",
                # Дублируем telegram_id в client_reference_id как запасной канал,
                # если в будущем metadata потеряется в промежуточном потоке.
                client_reference_id=str(telegram_id),
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

    def _notify_owner_via_api(
        *,
        actor_name: str,
        event: str,
        song_name: Optional[str] = None,
        payment_ok: Optional[bool] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Send an owner notification directly via the Telegram Bot API (no Bot instance)."""
        import html as _html

        owner_id = config.owner_telegram_id_int()
        if owner_id is None:
            return
        lines = [f"🛎 <b>{_html.escape(event)}</b>", f"User: {_html.escape(actor_name)}"]
        if song_name:
            lines.append(f"Track: {_html.escape(song_name)}")
        if payment_ok is True:
            lines.append("Payment: ✅ success")
        elif payment_ok is False:
            lines.append("Payment: ❌ failed")
        if reason:
            lines.append(f"Reason: {_html.escape(reason)}")
        try:
            requests.post(
                _tg_api_url("sendMessage"),
                json={"chat_id": owner_id, "text": "\n".join(lines), "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception:
            logger.exception("Failed to notify owner via Telegram API")

    @app.route("/webhook", methods=["POST"])
    def webhook() -> Any:
        def _session_metadata(session_obj: Any) -> dict[str, Any]:
            """
            Безопасно достаём metadata и из dict, и из StripeObject.

            У StripeObject нет метода .get(), из-за этого webhook падал 500.
            """
            try:
                if isinstance(session_obj, dict):
                    raw_meta = session_obj.get("metadata", {})
                else:
                    raw_meta = session_obj["metadata"]
            except Exception:
                return {}
            return raw_meta if isinstance(raw_meta, dict) else {}

        parsed = _parse_webhook_event(effective_wh_secret)
        if isinstance(parsed, tuple):
            return parsed
        event = parsed

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            meta = _session_metadata(session)
            telegram_id = str(meta.get("telegram_id") or "")
            song_id = str(meta.get("song_id") or "")
            telegram_name = str(meta.get("telegram_name") or "Unknown user")
            if not telegram_id:
                # Fallback: иногда client_reference_id есть, а metadata пустая.
                try:
                    telegram_id = str(session["client_reference_id"] or "")
                except Exception:
                    telegram_id = ""
            if not telegram_id or not song_id:
                event_id = str(event.get("id") or "unknown")
                logger.warning(
                    "Webhook metadata is incomplete: telegram_id or song_id missing (event_id=%s, telegram_id=%r, song_id=%r)",
                    event_id,
                    telegram_id,
                    song_id,
                )
                return "", 200
            song_name = str(get_catalog().get(song_id, {}).get("name") or song_id)
            try:
                deliver_purchase(
                    int(telegram_id),
                    song_id,
                    get_catalog(),
                    root_path(),
                )
                _notify_owner_via_api(
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=True,
                )
            except OSError as e:
                logger.exception("Failed to send audio: %s", e)
                _notify_owner_via_api(
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=False,
                    reason="Audio delivery failed",
                )
            except KeyError:
                logger.exception("Unknown song in webhook metadata: %s", song_id)
                _notify_owner_via_api(
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_id,
                    payment_ok=False,
                    reason="Unknown song in metadata",
                )

        if event["type"] in ("checkout.session.expired", "checkout.session.async_payment_failed"):
            session = event["data"]["object"]
            meta = _session_metadata(session)
            song_id = str(meta.get("song_id") or "unknown")
            song_name = str(get_catalog().get(song_id, {}).get("name") or song_id)
            telegram_name = str(meta.get("telegram_name") or "Unknown user")
            _notify_owner_via_api(
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
