"""
Письма покупателю и владельцу магазина после успешной оплаты (Gmail SMTP).

Включение: ENABLE_PURCHASE_EMAIL=1 и GMAIL_USER + GMAIL_PASSWORD (app password).

SMTP (обязательные настройки):
  host = smtp.gmail.com
  port = 587
  TLS  = starttls() ДО login()
  login = GMAIL_USER / GMAIL_PASSWORD из .env
"""

from __future__ import annotations

import logging
import os
import re
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
    password = _gmail_password()
    return bool(user and password)


def purchase_emails_disabled_reason() -> str | None:
    """Почему письма выключены (для логов диагностики). None — включены."""
    if (os.environ.get("ENABLE_PURCHASE_EMAIL") or "").strip() != "1":
        return "ENABLE_PURCHASE_EMAIL is not '1'"
    if not (os.environ.get("GMAIL_USER") or "").strip():
        return "GMAIL_USER is empty"
    if not _gmail_password():
        return "GMAIL_PASSWORD is empty"
    return None


def _gmail_user() -> str:
    return (os.environ.get("GMAIL_USER") or "").strip()


def _gmail_password() -> str:
    """App password из .env; пробелы внутри часто копируют из Google — убираем."""
    raw = os.environ.get("GMAIL_PASSWORD") or ""
    return "".join(raw.split())


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
    """Список адресов владельца(ев) для уведомлений о покупке."""
    owner_raw = (os.environ.get("SHOP_OWNER_EMAIL") or "").strip()
    if owner_raw:
        parsed = _parse_email_addresses(owner_raw)
        if parsed:
            return parsed
    user = _gmail_user()
    return [user] if user else []


def _shop_owner_email() -> str:
    """Строка для логов: один адрес или несколько через запятую."""
    return ", ".join(_shop_owner_emails())


def _support_contact_line() -> str:
    return (os.environ.get("SUPPORT_CONTACT") or "").strip() or "Please contact us on Telegram."


def _smtp_startup_test_enabled() -> bool:
    """По умолчанию тест при старте включён, если purchase email включён. SMTP_STARTUP_TEST=0 — выкл."""
    raw = (os.environ.get("SMTP_STARTUP_TEST") or "").strip().lower()
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


def _log_smtp_exception(stage: str, exc: BaseException, *, to_addr: str) -> None:
    """Подробный лог SMTP-ошибки без пароля."""
    user = _gmail_user()
    details = [
        f"stage={stage}",
        f"host={_GMAIL_SMTP_HOST}",
        f"port={_GMAIL_SMTP_PORT}",
        f"from={user!r}",
        f"to={to_addr!r}",
        f"exc_type={type(exc).__name__}",
        f"exc={exc!r}",
    ]
    if isinstance(exc, smtplib.SMTPResponseException):
        details.append(f"smtp_code={getattr(exc, 'smtp_code', None)!r}")
        details.append(f"smtp_error={getattr(exc, 'smtp_error', None)!r}")
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        details.append(
            "hint=Check GMAIL_USER and Gmail App Password (2FA required; "
            "regular account password will not work)."
        )
    if isinstance(exc, (TimeoutError, OSError, smtplib.SMTPConnectError)):
        details.append("hint=Network/firewall may block outbound TCP 587 to smtp.gmail.com.")
    logger.error("Gmail SMTP failed: %s", " | ".join(details), exc_info=True)


def _send_smtp(*, to_addr: str, subject: str, body: str) -> None:
    """
    Отправка через Gmail SMTP:
      smtp.gmail.com:587 → ehlo → starttls() → ehlo → login(GMAIL_USER, GMAIL_PASSWORD) → send.
    """
    from_addr = _gmail_user()
    password = _gmail_password()
    if not from_addr:
        raise RuntimeError("GMAIL_USER is empty — cannot send email")
    if not password:
        raise RuntimeError("GMAIL_PASSWORD is empty — cannot send email")
    if not (to_addr or "").strip():
        raise RuntimeError("Recipient address is empty — cannot send email")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    logger.info(
        "Gmail SMTP sending: host=%s port=%s tls=starttls login_user=%r to=%r subject=%r password_len=%s",
        _GMAIL_SMTP_HOST,
        _GMAIL_SMTP_PORT,
        from_addr,
        to_addr,
        subject,
        len(password),
    )

    smtp: smtplib.SMTP | None = None
    try:
        logger.debug("Gmail SMTP: connecting to %s:%s …", _GMAIL_SMTP_HOST, _GMAIL_SMTP_PORT)
        smtp = smtplib.SMTP(_GMAIL_SMTP_HOST, _GMAIL_SMTP_PORT, timeout=30)
        logger.debug("Gmail SMTP: connected, calling ehlo()")
        smtp.ehlo()
        logger.debug("Gmail SMTP: calling starttls() before login")
        smtp.starttls()
        logger.debug("Gmail SMTP: starttls OK, calling ehlo() again")
        smtp.ehlo()
        logger.debug("Gmail SMTP: calling login(%r, ***)", from_addr)
        smtp.login(from_addr, password)
        logger.debug("Gmail SMTP: login OK, calling send_message()")
        smtp.send_message(msg)
        logger.info("Gmail SMTP: message accepted for delivery to=%r subject=%r", to_addr, subject)
    except smtplib.SMTPAuthenticationError as e:
        _log_smtp_exception("login", e, to_addr=to_addr)
        raise
    except smtplib.SMTPRecipientsRefused as e:
        _log_smtp_exception("recipients", e, to_addr=to_addr)
        raise
    except smtplib.SMTPSenderRefused as e:
        _log_smtp_exception("sender", e, to_addr=to_addr)
        raise
    except smtplib.SMTPDataError as e:
        _log_smtp_exception("data", e, to_addr=to_addr)
        raise
    except smtplib.SMTPConnectError as e:
        _log_smtp_exception("connect", e, to_addr=to_addr)
        raise
    except smtplib.SMTPException as e:
        _log_smtp_exception("smtp", e, to_addr=to_addr)
        raise
    except OSError as e:
        _log_smtp_exception("os/network", e, to_addr=to_addr)
        raise
    except Exception as e:
        _log_smtp_exception("unexpected", e, to_addr=to_addr)
        raise
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass


def send_smtp_startup_test_email() -> bool:
    """
    Простое тестовое письмо при старте (проверка smtp.gmail.com:587 + starttls + login).

    Возвращает True при успехе. Ошибки только логируются (не роняют процесс).
    """
    reason = purchase_emails_disabled_reason()
    if reason:
        logger.warning("SMTP startup test skipped: %s", reason)
        return False
    if not _smtp_startup_test_enabled():
        logger.info("SMTP startup test skipped: SMTP_STARTUP_TEST is off")
        return False

    owners = _shop_owner_emails()
    if not owners:
        logger.warning("SMTP startup test skipped: no owner email (SHOP_OWNER_EMAIL / GMAIL_USER)")
        return False

    subject = "Music Acupuncture — SMTP startup test"
    body = (
        "This is an automatic test email from Music Acupuncture sell-bot.\n"
        "If you received it, Gmail SMTP works:\n"
        f"  server={_GMAIL_SMTP_HOST}\n"
        f"  port={_GMAIL_SMTP_PORT}\n"
        "  TLS=starttls() before login\n"
        f"  login user={_gmail_user()}\n"
    )
    ok_any = False
    for to_addr in owners:
        try:
            logger.info("SMTP startup test: sending test email to %r …", to_addr)
            _send_smtp(to_addr=to_addr, subject=subject, body=body)
            logger.info("SMTP startup test: SUCCESS — test email sent to %r", to_addr)
            ok_any = True
        except Exception as e:
            logger.error(
                "SMTP startup test: FAILED for %r — email will not work until this is fixed. error=%r",
                to_addr,
                e,
                exc_info=True,
            )
    return ok_any


def run_smtp_startup_test_if_configured() -> None:
    """Точка входа для bot/web startup (безопасно вызывать всегда)."""
    try:
        send_smtp_startup_test_email()
    except Exception:
        logger.exception("SMTP startup test: unexpected outer failure")


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
    disabled = purchase_emails_disabled_reason()
    if disabled:
        logger.warning(
            "purchase email: SKIPPED after purchase — %s (set ENABLE_PURCHASE_EMAIL=1, "
            "GMAIL_USER, GMAIL_PASSWORD in .env)",
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

    logger.info(
        "purchase email: start track=%r source=%s buyer_email=%r owners=%r has_drive_link=%s",
        title,
        source,
        buyer_to or None,
        _shop_owner_emails(),
        bool(link),
    )

    owners = _shop_owner_emails()
    if not owners:
        logger.error("purchase email: owner address empty — cannot notify owner")
    else:
        owner_body = _build_owner_body(
            track_title=title,
            buyer_label=owner_buyer,
            amount=amount,
            currency=currency,
            purchased_at_utc=purchased_at_utc,
            source=source,
        )
        owner_subject = f"New purchase – {title}"
        for owner_to in owners:
            try:
                _send_smtp(
                    to_addr=owner_to,
                    subject=owner_subject,
                    body=owner_body,
                )
                logger.info("purchase email: owner notified track=%r to=%r", title, owner_to)
            except Exception as e:
                logger.exception(
                    "purchase email: failed to send owner notification to %r: %r",
                    owner_to,
                    e,
                )

    if not buyer_to:
        logger.warning(
            "purchase email: no buyer email — skipping buyer message track=%r "
            "(Telegram Payments often has no email; website Stripe checkout may have customer_email)",
            title,
        )
        return

    try:
        _send_smtp(
            to_addr=buyer_to,
            subject=f"Your purchase – {title}",
            body=_build_buyer_body(track_title=title, download_link=link),
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
