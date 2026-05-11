from __future__ import annotations

import logging
import os
import hmac
import hashlib
import time
from urllib.parse import urlencode
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
import stripe
from flask import Flask, jsonify, redirect, request, send_from_directory

from music_sales import config
from music_sales.catalog import (
    discover_songs,
    free_bonus_audio_path,
    project_root,
    resolve_song_id_by_audio_stem,
    songs_dir_under,
    unit_amount_for_song,
)
from music_sales.file_id_delivery import PURCHASE_DELIVERY_CAPTION, file_id_for_song, load_file_ids_dict
from music_sales.mp3_duration import miniapp_track_durations_for_pricing

logger = logging.getLogger(__name__)


def _stripe_metadata_as_plain_dict(raw: Any) -> dict[str, Any]:
    """
    Webhook Stripe часто отдаёт metadata не как dict, а как StripeObject.
    Раньше мы возвращали {} → теряли source=website и слали MP3 в chat_id=0.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    to_dict = getattr(raw, "to_dict", None)
    if callable(to_dict):
        try:
            d = to_dict()
            if isinstance(d, dict):
                return dict(d)
        except Exception:
            pass
    try:
        keys = getattr(raw, "keys", None)
        if callable(keys):
            return {str(k): raw[k] for k in keys()}  # type: ignore[index]
    except Exception:
        pass
    return {}


def _checkout_session_payment_status(sess: Any) -> str:
    """payment_status из ответа Session.retrieve (dict или StripeObject)."""
    try:
        if isinstance(sess, dict):
            return str(sess.get("payment_status") or "")
        if hasattr(sess, "get"):
            return str(sess.get("payment_status") or "")
        return str(sess["payment_status"] or "")
    except Exception:
        return ""


def _checkout_session_metadata_plain(sess: Any) -> dict[str, Any]:
    """metadata из Session.retrieve — всегда приводим к dict (как в webhook)."""
    try:
        if isinstance(sess, dict):
            raw = sess.get("metadata")
        elif hasattr(sess, "get"):
            raw = sess.get("metadata")
        else:
            raw = sess["metadata"]
    except Exception:
        raw = {}
    return _stripe_metadata_as_plain_dict(raw)


def _miniapp_track_durations_payload() -> list:
    """Не ломаем /miniapp-pricing, если разбор MP3 или каталога упал."""
    try:
        return miniapp_track_durations_for_pricing()
    except Exception:
        logger.exception("miniapp track_durations")
        return []


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
    """
    Отправка покупки в Telegram по file_id из FILE_IDS_JSON (без локальных MP3).

    upload_songs.py загружает файлы через send_document — тот же тип file_id
    нужно отправлять через sendDocument (sendAudio с document file_id часто даёт 400).
    Параметр root оставлен для совместимости вызовов; диск для доставки не читаем.
    """
    _ = root  # явно не используем — см. докстринг
    song = songs_catalog[song_id]
    file_ids = load_file_ids_dict()
    fid = file_id_for_song(song, file_ids)
    if not fid:
        raise OSError(
            "No Telegram file_id for this track (check FILE_IDS_JSON keys vs upload_songs.py stems)."
        )
    title = str(song.get("name") or song_id)
    resp = requests.post(
        _tg_api_url("sendDocument"),
        data={
            "chat_id": telegram_id,
            "document": fid,
            "caption": PURCHASE_DELIVERY_CAPTION,
        },
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
            # GET — для /website/download и выдачи MP3 после оплаты с GitHub Pages
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        }

    def _path_is_checkout_cors() -> bool:
        """Пути Mini App / website → backend: checkout, цены и скачивание после Stripe (CORS)."""
        p = (request.path or "").rstrip("/") or ""
        tails = ("/create-checkout", "/create-payment", "/website-create-payment", "/miniapp-pricing")
        if p in (
            "/create-checkout",
            "/create-payment",
            "/website-create-payment",
            "/miniapp-pricing",
            "/website/download",
            "/website/download-redirect",
            "/website/download-file",
            "/free-track",
            "/free-track-file",
        ):
            return True
        return p.endswith(tails)

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

    def _checkout_success_url() -> str:
        """
        URL возврата после успешной оплаты.

        Если задан CHECKOUT_SUCCESS_URL (например, https://t.me/<bot_username>),
        Stripe после оплаты вернёт пользователя сразу в Telegram.
        """
        custom = (config.CHECKOUT_SUCCESS_URL or "").strip()
        if custom.startswith("https://"):
            return custom
        return domain + "/success"

    def _song_id_from_track_id(track_id_raw: Any) -> str | None:
        try:
            from pathlib import Path as _Path
            from tracks import get_track as _get_track

            t = _get_track(int(track_id_raw))
        except (ImportError, ValueError, TypeError, AttributeError):
            t = None
        if not t:
            return None
        stem = _Path(str(t.get("audio", ""))).stem
        return resolve_song_id_by_audio_stem(stem) if stem else None

    def _website_success_url(track_id_raw: Any) -> str:
        base = (os.environ.get("WEBSITE_SUCCESS_URL") or "").strip()
        if not base:
            base = "https://ianaranovitch-swe.github.io/Musicacupuncture-sell-bot/website.html"
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}success=true&track_id={track_id_raw}&session_id={{CHECKOUT_SESSION_ID}}"

    def _website_download_sign(song_id: str, exp: int) -> str:
        secret = (config.MINIAPP_CHECKOUT_SECRET or config.BOT_TOKEN or "fallback-secret").encode("utf-8")
        payload = f"{song_id}:{exp}".encode("utf-8")
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    @app.route("/miniapp.html")
    def miniapp_page() -> Any:
        """Статическая страница Telegram Mini App (один HTML-файл в корне репозитория)."""
        return send_from_directory(str(root_path()), "miniapp.html", mimetype="text/html")

    @app.route("/about.html")
    def about_michael_page() -> Any:
        """Страница о создателе MusicAcupuncture® (Michael B. Johnsson)."""
        return send_from_directory(str(root_path()), "about.html", mimetype="text/html")

    @app.route("/website.html")
    def website_landing_page() -> Any:
        """Публичная витрина (тот же файл, что на GitHub Pages); ссылка «Back» из about.html ведёт сюда."""
        return send_from_directory(str(root_path()), "website.html", mimetype="text/html")

    @app.route("/assets/<path:filename>")
    def static_assets(filename: str) -> Any:
        """Публичные файлы из папки assets/ (портрет для about.html и т.д.)."""
        assets_dir = (root_path() / "assets").resolve()
        try:
            target = (assets_dir / filename).resolve()
        except OSError:
            return jsonify({"error": "Invalid path"}), 400
        try:
            target.relative_to(assets_dir)
        except ValueError:
            return jsonify({"error": "Invalid path"}), 400
        if not target.is_file():
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(str(assets_dir), filename)

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
                    "track_durations": _miniapp_track_durations_payload(),
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
                "track_durations": _miniapp_track_durations_payload(),
            }
        )

    @app.route("/create-checkout", methods=["OPTIONS"])
    @app.route("/create-payment", methods=["OPTIONS"])
    @app.route("/website-create-payment", methods=["OPTIONS"])
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
                success_url=_checkout_success_url(),
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

    @app.route("/website-create-payment", methods=["POST"])
    def website_create_payment() -> Any:
        """
        Checkout для публичного website.html без Telegram initData и без MINIAPP_CHECKOUT_SECRET.
        Используем track_id -> song_id через tracks.py и каталог discover_songs().
        """
        data = request.get_json(silent=True) or {}
        track_id = data.get("track_id")
        currency = str(data.get("currency") or "usd").strip().lower()
        if track_id is None:
            return jsonify({"error": "track_id is required"}), 400
        if currency not in SUPPORTED_CHECKOUT_CURRENCIES:
            return jsonify({"error": "Unsupported currency"}), 400

        song_id = _song_id_from_track_id(track_id)
        if not song_id:
            return jsonify({"error": "Unknown track_id"}), 400

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
                success_url=_website_success_url(track_id),
                cancel_url=domain + "/cancel",
                client_reference_id="0",
                metadata={
                    "telegram_id": "0",
                    "telegram_name": "Website customer",
                    "song_id": song_id,
                    "source": "website",
                },
            )
        except stripe.error.StripeError as e:
            logger.exception("Website Stripe checkout failed: %s", e)
            return jsonify({"error": "Payment provider error"}), 502
        return jsonify({"url": session.url})

    def _website_signed_mp3_abs_url_or_error(session_id: str, track_id: str) -> Union[str, Tuple[dict[str, Any], int]]:
        """
        Проверка Stripe Checkout + подпись ссылки на MP3.
        Успех: абсолютный URL …/website/download-file?…
        Ошибка: (dict для jsonify, http_code).
        """
        if not session_id or not track_id:
            return ({"error": "session_id and track_id are required"}, 400)

        song_id = _song_id_from_track_id(track_id)
        if not song_id:
            return ({"error": "Unknown track_id"}, 400)

        try:
            sess = stripe.checkout.Session.retrieve(session_id)
        except Exception as e:
            logger.warning("website download: Stripe session retrieve failed: %s", e)
            return ({"error": "Invalid session"}, 400)

        payment_status = _checkout_session_payment_status(sess)
        if payment_status not in ("paid", "no_payment_required"):
            return ({"error": "Payment is not completed"}, 403)

        meta = _checkout_session_metadata_plain(sess)
        source = str(meta.get("source") or "").strip()
        sess_song_id = str(meta.get("song_id") or "").strip()
        if source != "website" or sess_song_id != song_id.strip():
            return ({"error": "Session metadata mismatch"}, 403)

        exp = int(time.time()) + 300
        sig = _website_download_sign(song_id, exp)
        qs = urlencode({"song_id": song_id, "exp": exp, "sig": sig})
        base = (request.url_root or "").rstrip("/") or domain
        return f"{base}/website/download-file?{qs}"

    @app.route("/website/download-redirect", methods=["GET"])
    def website_download_redirect() -> Any:
        """
        Редирект на подписанный MP3 — работает по обычной ссылке <a href> с GitHub Pages
        без CORS (в отличие от fetch к /website/download).
        """
        session_id = (request.args.get("session_id") or "").strip()
        track_id = (request.args.get("track_id") or "").strip()
        out = _website_signed_mp3_abs_url_or_error(session_id, track_id)
        if isinstance(out, tuple):
            return jsonify(out[0]), out[1]
        return redirect(out, code=302)

    @app.route("/website/download", methods=["GET", "OPTIONS"])
    def website_download() -> Any:
        """Проверяем Stripe session и выдаём одноразовый URL скачивания MP3 для website (JSON, нужен CORS)."""
        if request.method == "OPTIONS":
            return "", 204
        session_id = (request.args.get("session_id") or "").strip()
        track_id = (request.args.get("track_id") or "").strip()
        out = _website_signed_mp3_abs_url_or_error(session_id, track_id)
        if isinstance(out, tuple):
            return jsonify(out[0]), out[1]
        return jsonify({"url": out})

    @app.route("/website/download-file", methods=["GET", "OPTIONS"])
    def website_download_file() -> Any:
        """Отдаём MP3-файл как attachment по короткоживущей подписи."""
        if request.method == "OPTIONS":
            return "", 204
        song_id = (request.args.get("song_id") or "").strip()
        exp_raw = (request.args.get("exp") or "").strip()
        sig = (request.args.get("sig") or "").strip()
        if not song_id or not exp_raw or not sig:
            return jsonify({"error": "Invalid token"}), 400
        try:
            exp = int(exp_raw)
        except ValueError:
            return jsonify({"error": "Invalid token"}), 400
        if exp < int(time.time()):
            return jsonify({"error": "Token expired"}), 403
        expected = _website_download_sign(song_id, exp)
        if not hmac.compare_digest(sig, expected):
            return jsonify({"error": "Invalid token"}), 403

        catalog = get_catalog()
        song = catalog.get(song_id)
        if not song:
            return jsonify({"error": "Unknown song"}), 404
        rel = str(song.get("file") or "").strip()
        if not rel:
            return jsonify({"error": "Missing file path"}), 404
        p = (root_path() / rel).resolve()
        songs_root = (root_path() / "songs").resolve()
        try:
            p.relative_to(songs_root)
        except ValueError:
            return jsonify({"error": "Invalid path"}), 400
        if not p.is_file():
            return jsonify({"error": "File not found"}), 404
        return send_from_directory(str(p.parent), p.name, as_attachment=True, download_name=p.name)

    def _free_bonus_mp3_or_error() -> Union[Path, Tuple[Any, int]]:
        """Путь к бонусному MP3 внутри songs_dir() или (json_error, status)."""
        p = free_bonus_audio_path(root_path()).resolve()
        allowed = songs_dir_under(root_path()).resolve()
        try:
            p.relative_to(allowed)
        except ValueError:
            return jsonify({"error": "Invalid free track path"}), 500
        if not p.is_file():
            return jsonify({"error": "Free track file not available on server"}), 404
        return p

    @app.route("/free-track", methods=["GET", "OPTIONS"])
    def free_track_json() -> Any:
        """
        Публичная ссылка для website.html: JSON { "url": "…/free-track-file" }.
        Браузер на GitHub Pages делает fetch (нужен CORS — см. _path_is_checkout_cors).
        """
        if request.method == "OPTIONS":
            return "", 204
        out = _free_bonus_mp3_or_error()
        if isinstance(out, tuple):
            return out[0], out[1]
        base = (request.url_root or "").rstrip("/") or (domain or "").rstrip("/")
        if base and not base.startswith("http"):
            base = f"https://{base}"
        url = f"{base}/free-track-file" if base else "/free-track-file"
        return jsonify({"url": url})

    @app.route("/free-track-file", methods=["GET", "OPTIONS"])
    def free_track_file() -> Any:
        """Отдаёт бонусный MP3 как attachment (без оплаты — для лендинга website.html)."""
        if request.method == "OPTIONS":
            return "", 204
        out = _free_bonus_mp3_or_error()
        if isinstance(out, tuple):
            return out[0], out[1]
        p = out
        return send_from_directory(str(p.parent), p.name, as_attachment=True, download_name=p.name)

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
            return _stripe_metadata_as_plain_dict(raw_meta)

        def _recover_song_id_from_line_items(session_obj: Any, catalog: Dict[str, Dict[str, Any]]) -> str:
            """
            Запасной путь: если metadata.song_id пустой, пытаемся восстановить его по названию
            товара в Stripe line items (там хранится product_data.name).
            """
            try:
                session_id = str(session_obj["id"] or "")
            except Exception:
                return ""
            if not session_id:
                return ""
            try:
                li = stripe.checkout.Session.list_line_items(session_id, limit=5)
            except Exception:
                logger.warning("Could not load Stripe line items for session_id=%s", session_id)
                return ""
            data = li.get("data", []) if isinstance(li, dict) else getattr(li, "data", [])
            if not data:
                return ""

            names = {
                sid: str(meta.get("name") or "").strip().lower()
                for sid, meta in catalog.items()
                if str(meta.get("name") or "").strip()
            }
            for item in data:
                try:
                    # Stripe line item может прийти как dict или StripeObject.
                    if isinstance(item, dict):
                        desc = str(item.get("description") or "").strip()
                    else:
                        desc = str(item["description"] or "").strip()
                except Exception:
                    desc = ""
                if not desc:
                    continue
                normalized = desc.replace("[TEST] ", "").replace("[TEST]", "").strip().lower()
                for sid, nm in names.items():
                    if nm and nm == normalized:
                        return sid
            return ""

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
            source = str(meta.get("source") or "")
            catalog = get_catalog()
            if not telegram_id:
                # Fallback: иногда client_reference_id есть, а metadata пустая.
                try:
                    telegram_id = str(session["client_reference_id"] or "")
                except Exception:
                    telegram_id = ""
            if not song_id:
                # Fallback: если metadata.song_id пустой, пробуем восстановить из line items Stripe.
                song_id = _recover_song_id_from_line_items(session, catalog)
            if not telegram_id or not song_id:
                try:
                    event_id = str(event["id"] or "unknown")
                except Exception:
                    event_id = "unknown"
                logger.warning(
                    "Webhook metadata is incomplete: telegram_id or song_id missing (event_id=%s, telegram_id=%r, song_id=%r)",
                    event_id,
                    telegram_id,
                    song_id,
                )
                return "", 200
            song_name = str(catalog.get(song_id, {}).get("name") or song_id)
            try:
                tid_int = int(str(telegram_id).strip())
            except ValueError:
                tid_int = -1
            try:
                from music_sales.sales_log import append_sale_event

                try:
                    sess_id = str(session["id"] or "")
                except Exception:
                    sess_id = ""
                try:
                    transaction_id = str(session.get("payment_intent") or "")
                except Exception:
                    transaction_id = ""
                try:
                    amount_total = int(session.get("amount_total") or 0)
                except Exception:
                    amount_total = 0
                currency_code = str(session.get("currency") or "").upper()
                amount_major = (amount_total / 100.0) if amount_total > 0 else 0.0

                track_id_num = None
                try:
                    from pathlib import Path as _Path
                    from tracks import TRACKS as _TRACKS

                    for _t in _TRACKS:
                        _stem = _Path(str(_t.get("audio", ""))).stem
                        if _stem and resolve_song_id_by_audio_stem(_stem) == song_id:
                            track_id_num = int(_t.get("id"))
                            break
                except Exception:
                    track_id_num = None
                append_sale_event(
                    song_id=song_id,
                    track_id=track_id_num,
                    track_title=song_name,
                    amount=amount_major,
                    currency=currency_code,
                    source=(source or "telegram")[:32],
                    session_id=sess_id,
                    transaction_id=transaction_id,
                    telegram_id=tid_int if tid_int > 0 else None,
                )
            except Exception:
                logger.exception("sales_log append failed")

            # Website: не шлём документ в Telegram. Запасной путь: chat_id=0 невалиден в Telegram.
            if source == "website" or tid_int == 0:
                _notify_owner_via_api(
                    actor_name=telegram_name,
                    event="Payment result",
                    song_name=song_name,
                    payment_ok=True,
                    reason="Website sale — MP3 via site download (not Telegram).",
                )
                return "", 200
            try:
                deliver_purchase(
                    int(telegram_id),
                    song_id,
                    catalog,
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
        """
        Страница успеха после Stripe Checkout.

        Авто-возврат в Telegram после оплаты зависит от браузера/ОС, поэтому показываем
        понятную кнопку «Back to Telegram» и текст, где искать MP3.
        """
        back = (config.CHECKOUT_SUCCESS_URL or "").strip()
        if not back.startswith("https://"):
            back = "https://t.me"
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Payment successful</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 24px; line-height: 1.4; }}
      .box {{ max-width: 520px; margin: 0 auto; }}
      h1 {{ margin: 0 0 10px; }}
      p {{ margin: 8px 0; }}
      a.btn {{
        display: inline-block;
        margin-top: 14px;
        padding: 12px 16px;
        border-radius: 10px;
        background: #ffd700;
        color: #1a0533;
        font-weight: 700;
        text-decoration: none;
      }}
      .muted {{ color: #555; font-size: 0.95rem; }}
    </style>
  </head>
  <body>
    <div class="box">
      <h1>Payment successful</h1>
      <p>Your MP3 is sent in Telegram by the bot.</p>
      <p class="muted">If you don't see it yet, open the Telegram chat with the bot and wait a few seconds.</p>
      <a class="btn" href="{back}">Back to Telegram</a>
    </div>
  </body>
</html>"""

    @app.route("/cancel")
    def cancel() -> str:
        return "Payment cancelled."

    return app
