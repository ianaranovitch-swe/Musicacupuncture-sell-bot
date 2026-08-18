"""
Письма покупателю, владельцу магазина и разработчику после успешной оплаты (Resend API).

Включение: ENABLE_PURCHASE_EMAIL=1 и RESEND_API_KEY + RESEND_FROM.

Получатели:
  - buyer — email из Stripe Checkout (customer_details / customer_email)
  - owner(s) — SHOP_OWNER_EMAIL (несколько через , или ;)
  - developer(s) — DEVELOPER_EMAIL (несколько через , или ;)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from music_sales.email_templates import (
    build_buyer_email,
    build_staff_email,
    build_startup_test_email,
)

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


def purchase_emails_enabled() -> bool:
    if (os.environ.get("ENABLE_PURCHASE_EMAIL") or "").strip() != "1":
        return False
    return bool(_resend_api_key() and _resend_from())


def purchase_emails_disabled_reason() -> str | None:
    """Почему письма выключены (для логов диагностики). None — включены."""
    if (os.environ.get("ENABLE_PURCHASE_EMAIL") or "").strip() != "1":
        return "ENABLE_PURCHASE_EMAIL is not '1'"
    if not _resend_api_key():
        return "RESEND_API_KEY is empty"
    if not _resend_from():
        return "RESEND_FROM is empty"
    return None


def _resend_api_key() -> str:
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def _resend_from() -> str:
    """
    Отправитель Resend, например:
      Music Acupuncture <orders@musicacupuncture.digital>
      orders@musicacupuncture.digital
    """
    return (os.environ.get("RESEND_FROM") or "").strip()


def _parse_email_addresses(raw: str) -> list[str]:
    """
    Разбор одного или нескольких адресов из env.

    Примеры:
      owner@gmail.com
      owner1@gmail.com, owner2@gmail.com
      a@x.com; b@y.com
    """
    text = (raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[,;]+", text)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        addr = part.strip()
        if not addr or "@" not in addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return out


def _shop_owner_emails() -> list[str]:
    """Список адресов владельца(ев) / продавца для уведомлений о покупке."""
    owner_raw = (os.environ.get("SHOP_OWNER_EMAIL") or "").strip()
    if owner_raw:
        return _parse_email_addresses(owner_raw)
    return []


def _developer_emails() -> list[str]:
    """Адреса разработчика (проект + вы) — то же уведомление, что владельцу."""
    return _parse_email_addresses(os.environ.get("DEVELOPER_EMAIL") or "")


def _staff_notify_emails() -> list[str]:
    """Owner + developer без дублей (один человек может быть в обоих списках)."""
    out: list[str] = []
    seen: set[str] = set()
    for addr in _shop_owner_emails() + _developer_emails():
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return out


def _shop_owner_email() -> str:
    """Строка для логов: один адрес или несколько через запятую."""
    return ", ".join(_shop_owner_emails())


def _support_contact_line() -> str:
    return (os.environ.get("SUPPORT_CONTACT") or "").strip() or "Please contact us on Telegram."


def _email_startup_test_enabled() -> bool:
    """
    По умолчанию тест при старте включён, если purchase email включён.
    EMAIL_STARTUP_TEST / SMTP_STARTUP_TEST = 0 — выкл. (SMTP_* — совместимость со старым .env).
    """
    raw = (
        os.environ.get("EMAIL_STARTUP_TEST") or os.environ.get("SMTP_STARTUP_TEST") or ""
    ).strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return purchase_emails_enabled()


def drive_download_link(song_row: dict[str, Any]) -> str | None:
    """Публичная ссылка Google Drive из google_drive_file_id каталога."""
    from music_sales.gdrive_ids import google_drive_file_id_for_song, load_gdrive_ids_dict

    fid = google_drive_file_id_for_song(song_row, load_gdrive_ids_dict())
    if not fid:
        return None
    return f"https://drive.google.com/file/d/{fid}/view"


def _format_purchased_at(purchased_at_utc: datetime | None) -> str:
    dt = purchased_at_utc or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _staff_role_for_address(addr: str) -> str:
    """owner / developer / team — для заголовка staff-письма."""
    key = (addr or "").strip().lower()
    owners = {a.lower() for a in _shop_owner_emails()}
    developers = {a.lower() for a in _developer_emails()}
    in_o = key in owners
    in_d = key in developers
    if in_o and not in_d:
        return "owner"
    if in_d and not in_o:
        return "developer"
    return "team"


def _log_resend_exception(stage: str, exc: BaseException, *, to_addr: str) -> None:
    details = [
        f"stage={stage}",
        f"api={_RESEND_API_URL}",
        f"from={_resend_from()!r}",
        f"to={to_addr!r}",
        f"exc_type={type(exc).__name__}",
        f"exc={exc!r}",
    ]
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        details.append(f"http_status={exc.response.status_code}")
        try:
            details.append(f"response_body={exc.response.text[:500]!r}")
        except Exception:
            pass
        details.append(
            "hint=Check RESEND_API_KEY, verified RESEND_FROM domain, and Resend dashboard logs."
        )
    logger.error("Resend email failed: %s", " | ".join(details), exc_info=True)


def _send_email(*, to_addr: str, subject: str, body: str, html: str | None = None) -> None:
    """
    Отправка через Resend HTTP API:
      POST https://api.resend.com/emails
      Authorization: Bearer RESEND_API_KEY
    body — plain text; html — опциональный брендированный шаблон.
    """
    api_key = _resend_api_key()
    from_addr = _resend_from()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is empty — cannot send email")
    if not from_addr:
        raise RuntimeError("RESEND_FROM is empty — cannot send email")
    if not (to_addr or "").strip():
        raise RuntimeError("Recipient address is empty — cannot send email")

    payload: dict[str, Any] = {
        "from": from_addr,
        "to": [to_addr.strip()],
        "subject": subject,
        "text": body,
    }
    if html and str(html).strip():
        payload["html"] = html
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info(
        "Resend sending: from=%r to=%r subject=%r has_html=%s api_key_len=%s",
        from_addr,
        to_addr,
        subject,
        bool(html and str(html).strip()),
        len(api_key),
    )

    try:
        resp = requests.post(_RESEND_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code >= 400:
            logger.error(
                "Resend HTTP error: status=%s body=%r to=%r",
                resp.status_code,
                (resp.text or "")[:500],
                to_addr,
            )
            resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            data = {}
        email_id = data.get("id") if isinstance(data, dict) else None
        logger.info(
            "Resend: message accepted for delivery to=%r subject=%r id=%r",
            to_addr,
            subject,
            email_id,
        )
    except requests.HTTPError as e:
        _log_resend_exception("http", e, to_addr=to_addr)
        raise
    except requests.RequestException as e:
        _log_resend_exception("network", e, to_addr=to_addr)
        raise
    except Exception as e:
        _log_resend_exception("unexpected", e, to_addr=to_addr)
        raise


# Совместимость со старыми тестами/импортами (алиас на Resend).
def _send_smtp(*, to_addr: str, subject: str, body: str, html: str | None = None) -> None:
    _send_email(to_addr=to_addr, subject=subject, body=body, html=html)


def send_email_startup_test() -> bool:
    """
    Простое тестовое письмо при старте (проверка Resend API).

    Возвращает True при успехе. Ошибки только логируются (не роняют процесс).
    """
    reason = purchase_emails_disabled_reason()
    if reason:
        logger.warning("Email startup test skipped: %s", reason)
        return False
    if not _email_startup_test_enabled():
        logger.info("Email startup test skipped: EMAIL_STARTUP_TEST / SMTP_STARTUP_TEST is off")
        return False

    recipients = _staff_notify_emails()
    if not recipients:
        logger.warning(
            "Email startup test skipped: no staff email "
            "(set SHOP_OWNER_EMAIL and/or DEVELOPER_EMAIL)"
        )
        return False

    content = build_startup_test_email(from_addr=_resend_from(), api_url=_RESEND_API_URL)
    ok_any = False
    for to_addr in recipients:
        try:
            logger.info("Email startup test: sending test email to %r …", to_addr)
            _send_email(
                to_addr=to_addr,
                subject=content.subject,
                body=content.text,
                html=content.html,
            )
            logger.info("Email startup test: SUCCESS — test email sent to %r", to_addr)
            ok_any = True
        except Exception as e:
            logger.error(
                "Email startup test: FAILED for %r — email will not work until this is fixed. error=%r",
                to_addr,
                e,
                exc_info=True,
            )
    return ok_any

def send_smtp_startup_test_email() -> bool:
    """Алиас для совместимости со старым именем."""
    return send_email_startup_test()


def run_email_startup_test_if_configured() -> None:
    """Точка входа для bot/web startup (безопасно вызывать всегда)."""
    try:
        send_email_startup_test()
    except Exception:
        logger.exception("Email startup test: unexpected outer failure")


def run_smtp_startup_test_if_configured() -> None:
    """Алиас: bot_app / web_entry по-прежнему импортируют это имя."""
    run_email_startup_test_if_configured()


def send_purchase_emails(
    *,
    track_title: str,
    song_row: dict[str, Any],
    amount: float,
    currency: str,
    purchased_at_utc: datetime | None = None,
    buyer_email: str | None = None,
    buyer_telegram_label: str = "",
    source: str = "telegram",
) -> None:
    """
    Письма: staff (owner + developer) и покупателю (если есть email).
    HTML-шаблоны адаптируются под покупателя. Ошибки Resend только в лог.
    """
    disabled = purchase_emails_disabled_reason()
    if disabled:
        logger.warning(
            "purchase email: SKIPPED after purchase — %s (set ENABLE_PURCHASE_EMAIL=1, "
            "RESEND_API_KEY, RESEND_FROM in .env / Railway)",
            disabled,
        )
        return

    title = (track_title or str(song_row.get("name") or "Track")).strip() or "Track"
    link = drive_download_link(song_row)
    buyer_label = (buyer_telegram_label or "").strip() or "Unknown"
    buyer_to = (buyer_email or "").strip()
    owner_buyer = buyer_label
    if buyer_to and buyer_label in ("Unknown", ""):
        owner_buyer = buyer_to
    elif buyer_to and buyer_label not in ("Unknown", ""):
        owner_buyer = f"{buyer_label} ({buyer_to})"

    staff = _staff_notify_emails()
    logger.info(
        "purchase email: start track=%r source=%s buyer_email=%r staff=%r has_drive_link=%s",
        title,
        source,
        buyer_to or None,
        staff,
        bool(link),
    )

    purchased_label = _format_purchased_at(purchased_at_utc)

    if not staff:
        logger.error(
            "purchase email: staff address empty — set SHOP_OWNER_EMAIL and/or DEVELOPER_EMAIL"
        )
    else:
        for staff_to in staff:
            content = build_staff_email(
                track_title=title,
                buyer_label=owner_buyer,
                buyer_email=buyer_to or None,
                amount=amount,
                currency=currency,
                purchased_at=purchased_label,
                source=source,
                download_link=link,
                recipient_role=_staff_role_for_address(staff_to),
            )
            try:
                _send_email(
                    to_addr=staff_to,
                    subject=content.subject,
                    body=content.text,
                    html=content.html,
                )
                logger.info("purchase email: staff notified track=%r to=%r", title, staff_to)
            except Exception as e:
                logger.exception(
                    "purchase email: failed to send staff notification to %r: %r",
                    staff_to,
                    e,
                )

    if not buyer_to:
        logger.warning(
            "purchase email: no buyer email — skipping buyer message track=%r "
            "(Telegram Payments often has no email; website Stripe checkout may have customer_email)",
            title,
        )
        return

    buyer_content = build_buyer_email(
        track_title=title,
        download_link=link,
        buyer_email=buyer_to,
        buyer_label=buyer_label,
        amount=amount,
        currency=currency,
        support_contact=_support_contact_line(),
    )
    try:
        _send_email(
            to_addr=buyer_to,
            subject=buyer_content.subject,
            body=buyer_content.text,
            html=buyer_content.html,
        )
        logger.info("purchase email: buyer notified %s track=%r", buyer_to, title)
    except Exception as e:
        logger.exception("purchase email: failed to send buyer notification to %s: %r", buyer_to, e)

def buyer_email_from_checkout_session(session: Any) -> str | None:
    """Email из Stripe Checkout Session (website / external checkout)."""
    for key in ("customer_email",):
        try:
            if isinstance(session, dict):
                raw = session.get(key)
            else:
                raw = getattr(session, key, None)
            if raw:
                return str(raw).strip() or None
        except Exception:
            pass
    try:
        if isinstance(session, dict):
            details = session.get("customer_details")
        else:
            details = getattr(session, "customer_details", None)
        if details is not None:
            if isinstance(details, dict):
                em = details.get("email")
            else:
                em = getattr(details, "email", None)
            if em:
                return str(em).strip() or None
    except Exception:
        pass
    return None


def send_purchase_emails_for_stripe_session(
    session: Any,
    *,
    catalog: dict[str, Any],
    song_id: str,
    meta: dict[str, Any],
    telegram_id_int: int,
) -> None:
    """Вызов из webhook checkout.session.completed после успешной оплаты."""
    song_row = catalog.get(song_id) if isinstance(catalog.get(song_id), dict) else {}
    track_title = str(song_row.get("name") or song_id)
    try:
        amount_total = (
            int(session.get("amount_total") or 0)
            if isinstance(session, dict)
            else int(getattr(session, "amount_total", None) or 0)
        )
    except (TypeError, ValueError):
        amount_total = 0
    try:
        currency_code = (
            str(session.get("currency") or "")
            if isinstance(session, dict)
            else str(getattr(session, "currency", "") or "")
        ).upper()
    except Exception:
        currency_code = "USD"
    amount_major = (amount_total / 100.0) if amount_total > 0 else 0.0
    source = str(meta.get("source") or "telegram").strip() or "telegram"
    telegram_name = str(meta.get("telegram_name") or "")
    send_purchase_emails(
        track_title=track_title,
        song_row=song_row,
        amount=amount_major,
        currency=currency_code or "USD",
        buyer_email=buyer_email_from_checkout_session(session),
        buyer_telegram_label=buyer_label_from_metadata(
            telegram_name,
            telegram_id_int if telegram_id_int > 0 else None,
        ),
        source=source,
    )


def buyer_label_from_metadata(telegram_name: str, telegram_id: int | None = None) -> str:
    """Подпись покупателя для письма владельцу."""
    name = (telegram_name or "").strip()
    if name and name.lower() not in ("unknown user", "website customer", "unknown"):
        if name.startswith("@"):
            return name
        if " " not in name and name.isascii() and name.replace("_", "").isalnum():
            return f"@{name.lstrip('@')}"
        return name
    if telegram_id is not None and telegram_id > 0:
        return f"Telegram user id {telegram_id}"
    return "Unknown"
