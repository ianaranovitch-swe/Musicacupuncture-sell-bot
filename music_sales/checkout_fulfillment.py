"""
Общая логика после успешной оплаты Stripe Checkout.

Вызывается из webhook checkout.session.completed и (запасной путь) при первой
проверке оплаты на /website/download* — если live webhook не настроен или подпись неверна.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

import requests
import stripe
from tracks import TRACKS

from music_sales.owner_notify import notify_owner_http
from music_sales.purchase_email import send_purchase_emails_for_stripe_session
from music_sales.sales_log import append_sale_event, sale_event_exists_for_session

logger = logging.getLogger(__name__)


def stripe_metadata_as_plain_dict(raw: Any) -> dict[str, Any]:
    """metadata из Stripe (dict или StripeObject) → обычный dict."""
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


def checkout_session_metadata_plain(sess: Any) -> dict[str, Any]:
    """metadata из Session (retrieve или webhook object)."""
    try:
        if isinstance(sess, dict):
            raw = sess.get("metadata")
        elif hasattr(sess, "get"):
            raw = sess.get("metadata")
        else:
            raw = sess["metadata"]
    except Exception:
        raw = {}
    return stripe_metadata_as_plain_dict(raw)


def _session_field(sess: Any, key: str, default: Any = "") -> Any:
    try:
        if isinstance(sess, dict):
            return sess.get(key, default)
        if hasattr(sess, "get"):
            return sess.get(key, default)
        return sess[key]
    except Exception:
        return default


def recover_song_id_from_line_items(session_obj: Any, catalog: dict[str, dict[str, Any]]) -> str:
    """Если metadata.song_id пустой — пробуем сопоставить description line item с каталогом."""
    session_id = str(_session_field(session_obj, "id") or "")
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


def _resolve_track_id_for_song_id(song_id: str) -> int | None:
    try:
        for t in TRACKS:
            stem = Path(str(t.get("audio") or "")).stem
            if stem and resolve_song_id_by_audio_stem(stem) == song_id:
                return int(t.get("id"))
    except Exception:
        pass
    return None


def _safe_notify_owner_http(*, session_id: str, **kwargs: Any) -> None:
    """Уведомление владельцу не должно ронять webhook / скачивание."""
    try:
        notify_owner_http(**kwargs)
    except Exception:
        logger.exception("checkout fulfillment: owner notify failed session_id=%s", session_id)


def fulfill_checkout_session_completed(
    session: Any,
    *,
    catalog: dict[str, dict[str, Any]],
    deliver_purchase_fn: Optional[Callable[..., None]] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """
    Журнал продаж + email + уведомление в Telegram (и выдача MP3 в боте для telegram checkout).

    Идемпотентно по session_id: повторный вызов (второй клик «скачать») ничего не дублирует.
    Возвращает True, если обработка выполнена впервые для этой сессии.
    """
    sess_id = str(_session_field(session, "id") or "").strip()
    if not sess_id:
        logger.warning("checkout fulfillment: session without id")
        return False

    if sale_event_exists_for_session(sess_id):
        logger.debug("checkout fulfillment: already processed session_id=%s", sess_id)
        return False

    meta = checkout_session_metadata_plain(session)
    telegram_id = str(meta.get("telegram_id") or "").strip()
    song_id = str(meta.get("song_id") or "").strip()
    telegram_name = str(meta.get("telegram_name") or "Unknown user")
    source = str(meta.get("source") or "").strip()

    if not telegram_id:
        telegram_id = str(_session_field(session, "client_reference_id") or "").strip()
    if not song_id:
        song_id = recover_song_id_from_line_items(session, catalog)

    is_website = source == "website"
    if not song_id:
        logger.warning(
            "checkout fulfillment: song_id missing session_id=%s source=%r",
            sess_id,
            source,
        )
        return False
    if not is_website and not telegram_id:
        logger.warning(
            "checkout fulfillment: telegram_id missing for bot checkout session_id=%s",
            sess_id,
        )
        return False

    song_name = str(catalog.get(song_id, {}).get("name") or song_id)
    try:
        tid_int = int(telegram_id)
    except ValueError:
        tid_int = -1

    try:
        transaction_id = str(_session_field(session, "payment_intent") or "")
    except Exception:
        transaction_id = ""
    try:
        amount_total = int(_session_field(session, "amount_total") or 0)
    except (TypeError, ValueError):
        amount_total = 0
    try:
        currency_code = str(getattr(session, "currency", "") or _session_field(session, "currency") or "").upper()
    except Exception:
        currency_code = "USD"
    amount_major = (amount_total / 100.0) if amount_total > 0 else 0.0
    track_id_num = _resolve_track_id_for_song_id(song_id)

    try:
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
        logger.exception("checkout fulfillment: sales_log append failed session_id=%s", sess_id)
        return False

    try:
        send_purchase_emails_for_stripe_session(
            session,
            catalog=catalog,
            song_id=song_id,
            meta=meta,
            telegram_id_int=tid_int,
        )
    except Exception:
        logger.exception("checkout fulfillment: purchase email failed session_id=%s", sess_id)

    if is_website or tid_int == 0:
        _safe_notify_owner_http(
            session_id=sess_id,
            actor_name=telegram_name,
            event="Payment result",
            song_name=song_name,
            payment_ok=True,
            reason="Website sale — MP3 via site download (not Telegram).",
        )
        logger.info("checkout fulfillment: website sale completed session_id=%s", sess_id)
        return True

    if deliver_purchase_fn is None or project_root is None:
        logger.warning(
            "checkout fulfillment: bot delivery skipped (no deliver_purchase_fn) session_id=%s",
            sess_id,
        )
        _safe_notify_owner_http(
            session_id=sess_id,
            actor_name=telegram_name,
            event="Payment result",
            song_name=song_name,
            payment_ok=True,
        )
        return True

    try:
        deliver_purchase_fn(int(telegram_id), song_id, catalog, project_root)
        _safe_notify_owner_http(
            session_id=sess_id,
            actor_name=telegram_name,
            event="Payment result",
            song_name=song_name,
            payment_ok=True,
        )
    except OSError as e:
        logger.exception("checkout fulfillment: deliver_purchase failed session_id=%s", sess_id)
        fail_reason = str(e).strip()[:220] or "Audio delivery failed"
        try:
            token = (config.BOT_TOKEN or "").strip()
            if token and tid_int > 0:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data={
                        "chat_id": tid_int,
                        "text": (
                            "Payment received — thank you! "
                            "We could not send your MP3 automatically. "
                            "Please contact support and mention this track name."
                        ),
                    },
                    timeout=30,
                )
        except Exception:
            logger.warning("checkout fulfillment: could not notify buyer about delivery failure")
        _safe_notify_owner_http(
            session_id=sess_id,
            actor_name=telegram_name,
            event="Payment result",
            song_name=song_name,
            payment_ok=False,
            reason=fail_reason,
        )
    except KeyError:
        logger.exception("checkout fulfillment: unknown song_id=%s session_id=%s", song_id, sess_id)
        _safe_notify_owner_http(
            session_id=sess_id,
            actor_name=telegram_name,
            event="Payment result",
            song_name=song_id,
            payment_ok=False,
            reason="Unknown song in metadata",
        )
    except Exception:
        logger.exception("checkout fulfillment: unexpected bot delivery error session_id=%s", sess_id)
        _safe_notify_owner_http(
            session_id=sess_id,
            actor_name=telegram_name,
            event="Payment result",
            song_name=song_name,
            payment_ok=False,
            reason="Audio delivery failed",
        )

    return True
