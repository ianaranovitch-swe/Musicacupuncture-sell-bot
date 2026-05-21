"""
Письма покупателю и владельцу магазина после успешной оплаты (Gmail SMTP).

Включение: ENABLE_PURCHASE_EMAIL=1 и GMAIL_USER + GMAIL_PASSWORD (app password).
"""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

logger = logging.getLogger(__name__)

_GMAIL_SMTP_HOST = "smtp.gmail.com"
_GMAIL_SMTP_PORT = 587


def purchase_emails_enabled() -> bool:
    if (os.environ.get("ENABLE_PURCHASE_EMAIL") or "").strip() != "1":
        return False
    user = (os.environ.get("GMAIL_USER") or "").strip()
    password = (os.environ.get("GMAIL_PASSWORD") or "").strip()
    return bool(user and password)


def _gmail_user() -> str:
    return (os.environ.get("GMAIL_USER") or "").strip()


def _shop_owner_email() -> str:
    owner = (os.environ.get("SHOP_OWNER_EMAIL") or "").strip()
    return owner or _gmail_user()


def _support_contact_line() -> str:
    return (os.environ.get("SUPPORT_CONTACT") or "").strip() or "Please contact us on Telegram."


def drive_download_link(song_row: dict[str, Any]) -> str | None:
    """Публичная ссылка Google Drive из google_drive_file_id каталога."""
    from music_sales.gdrive_ids import google_drive_file_id_for_song, load_gdrive_ids_dict

    fid = google_drive_file_id_for_song(song_row, load_gdrive_ids_dict())
    if not fid:
        return None
    return f"https://drive.google.com/file/d/{fid}/view"


def _format_amount(amount: float, currency: str) -> str:
    ccy = (currency or "USD").strip().upper()
    if ccy == "SEK":
        return f"{amount:.2f} kr"
    if ccy == "EUR":
        return f"€{amount:.2f}"
    return f"${amount:.2f}"


def _format_purchased_at(purchased_at_utc: datetime | None) -> str:
    dt = purchased_at_utc or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _build_buyer_body(*, track_title: str, download_link: str | None) -> str:
    lines = [
        "Thank you for your purchase from Music Acupuncture!",
        "",
        f"Track: {track_title}",
    ]
    if download_link:
        lines.extend(["", "Download your MP3 here:", download_link])
    else:
        lines.extend(["", "Your MP3 link will be sent separately if Drive is not configured for this track."])
    lines.extend(["", "Need help?", _support_contact_line(), "", "With gratitude,", "Michael — Music Acupuncture"])
    return "\n".join(lines)


def _build_owner_body(
    *,
    track_title: str,
    buyer_label: str,
    amount: float,
    currency: str,
    purchased_at_utc: datetime | None,
    source: str,
) -> str:
    src = (source or "telegram").strip() or "telegram"
    lines = [
        "New purchase on Music Acupuncture",
        "",
        f"Track: {track_title}",
        f"Buyer: {buyer_label}",
        f"Amount: {_format_amount(amount, currency)}",
        f"Date: {_format_purchased_at(purchased_at_utc)}",
        f"Source: {src}",
    ]
    return "\n".join(lines)


def _send_smtp(*, to_addr: str, subject: str, body: str) -> None:
    from_addr = _gmail_user()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP(_GMAIL_SMTP_HOST, _GMAIL_SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(from_addr, (os.environ.get("GMAIL_PASSWORD") or "").strip())
        smtp.send_message(msg)


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
    Два письма: покупателю (если есть email) и владельцу. Ошибки SMTP только в лог — не роняют webhook/бот.
    """
    if not purchase_emails_enabled():
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

    try:
        owner_to = _shop_owner_email()
        if owner_to:
            _send_smtp(
                to_addr=owner_to,
                subject=f"New purchase – {title}",
                body=_build_owner_body(
                    track_title=title,
                    buyer_label=owner_buyer,
                    amount=amount,
                    currency=currency,
                    purchased_at_utc=purchased_at_utc,
                    source=source,
                ),
            )
            logger.info("purchase email: owner notified track=%r", title)
    except Exception:
        logger.exception("purchase email: failed to send owner notification")

    if not buyer_to:
        logger.debug("purchase email: no buyer email — skipping buyer message track=%r", title)
        return

    try:
        _send_smtp(
            to_addr=buyer_to,
            subject=f"Your purchase – {title}",
            body=_build_buyer_body(track_title=title, download_link=link),
        )
        logger.info("purchase email: buyer notified %s track=%r", buyer_to, title)
    except Exception:
        logger.exception("purchase email: failed to send buyer notification to %s", buyer_to)


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
        amount_total = int(session.get("amount_total") or 0) if isinstance(session, dict) else int(
            getattr(session, "amount_total", None) or 0
        )
    except (TypeError, ValueError):
        amount_total = 0
    try:
        currency_code = (
            str(session.get("currency") or "") if isinstance(session, dict) else str(getattr(session, "currency", "") or "")
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
