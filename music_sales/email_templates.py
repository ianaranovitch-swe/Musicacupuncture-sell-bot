"""
HTML + plain-text шаблоны писем Music Acupuncture (покупатель / staff).

Стиль: тёмный фон #1a0533, золото #ffd700 — как витрина. Табличная вёрстка для email-клиентов.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass


# Цвета бренда (как на сайте)
_BG = "#1a0533"
_GOLD = "#ffd700"
_TEXT = "#ffffff"
_MUTED = "#c9b8e8"
_CARD = "#2a1050"
_BORDER = "rgba(255, 215, 0, 0.35)"


@dataclass(frozen=True)
class EmailContent:
    """Готовый текст письма: subject + plain + html."""

    subject: str
    text: str
    html: str


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _store_url() -> str:
    """Ссылка на витрину для кнопки в письме."""
    for key in ("WEBSITE_SUCCESS_URL", "DOMAIN", "BACKEND_URL"):
        raw = (os.environ.get(key) or "").strip().rstrip("/")
        if not raw:
            continue
        if raw.startswith("http://") or raw.startswith("https://"):
            parts = raw.split("/", 3)
            if len(parts) >= 3:
                return f"{parts[0]}//{parts[2]}"
            return raw
        return f"https://{raw}"
    return "https://musicacupuncture.digital"


def format_money(amount: float, currency: str) -> str:
    ccy = (currency or "USD").strip().upper()
    if ccy == "SEK":
        return f"{amount:.2f} kr"
    if ccy == "EUR":
        return f"€{amount:.2f}"
    return f"${amount:.2f}"


def buyer_display_name(*, buyer_email: str | None, buyer_label: str | None) -> str:
    """
    Имя для приветствия: из Telegram-лейбла, иначе из локальной части email.
    Примеры: @sarah → Sarah; buyer@x.com → Buyer; Unknown → Friend.
    """
    label = (buyer_label or "").strip()
    if label and label.lower() not in ("unknown", "unknown user", "website customer"):
        if label.startswith("@"):
            name = label[1:].replace("_", " ").strip()
        elif label.lower().startswith("telegram user id"):
            name = ""
        else:
            name = label.replace("_", " ").strip()
        if name:
            parts = [p[:1].upper() + p[1:] if p else p for p in name.split()]
            return " ".join(parts)

    email = (buyer_email or "").strip()
    if email and "@" in email:
        local = email.split("@", 1)[0]
        local = re.sub(r"[._+\-]+", " ", local).strip()
        if local:
            parts = [p[:1].upper() + p[1:] if p else p for p in local.split()]
            return " ".join(parts) or "Friend"
    return "Friend"


def _shell(*, title: str, eyebrow: str, inner_html: str, footer_note: str) -> str:
    """Общая рамка письма (table layout)."""
    store = _esc(_store_url())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:Georgia,'Times New Roman',serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{_BG};padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;background:{_CARD};border:1px solid {_BORDER};border-radius:16px;overflow:hidden;">
          <tr>
            <td style="padding:28px 28px 12px;text-align:center;background:{_CARD};">
              <p style="margin:0 0 8px;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:{_GOLD};font-family:Arial,Helvetica,sans-serif;font-weight:700;">
                {_esc(eyebrow)}
              </p>
              <h1 style="margin:0;font-size:26px;line-height:1.25;color:{_GOLD};font-weight:700;">
                Music Acupuncture
              </h1>
              <p style="margin:8px 0 0;font-size:14px;color:{_MUTED};font-family:Arial,Helvetica,sans-serif;">
                Divine Healing Sounds
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 28px;color:{_TEXT};font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.55;">
              {inner_html}
            </td>
          </tr>
          <tr>
            <td style="padding:18px 28px 24px;border-top:1px solid {_BORDER};text-align:center;">
              <p style="margin:0 0 10px;font-size:13px;color:{_MUTED};font-family:Arial,Helvetica,sans-serif;">
                {_esc(footer_note)}
              </p>
              <a href="{store}" style="display:inline-block;padding:10px 18px;border-radius:999px;background:{_GOLD};color:{_BG};text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;">
                Visit the store
              </a>
              <p style="margin:14px 0 0;font-size:11px;color:{_MUTED};font-family:Arial,Helvetica,sans-serif;">
                © Music Acupuncture® · Michael B. Johnsson
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _detail_row(label: str, value: str) -> str:
    return f"""
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.08);color:{_MUTED};font-size:13px;width:34%;vertical-align:top;">{_esc(label)}</td>
                <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.08);color:{_TEXT};font-size:14px;font-weight:600;">{_esc(value)}</td>
              </tr>"""


def build_buyer_email(
    *,
    track_title: str,
    download_link: str | None,
    buyer_email: str | None,
    buyer_label: str | None,
    amount: float | None = None,
    currency: str | None = None,
    support_contact: str,
) -> EmailContent:
    """Персональное письмо покупателю после оплаты."""
    name = buyer_display_name(buyer_email=buyer_email, buyer_label=buyer_label)
    title = (track_title or "Your track").strip() or "Your track"
    subject = f"Your purchase — {title}"

    amount_line = ""
    if amount is not None and currency:
        amount_line = format_money(amount, currency)

    text_lines = [
        f"Dear {name},",
        "",
        "Thank you for your purchase from Music Acupuncture!",
        "",
        f"Track: {title}",
    ]
    if amount_line:
        text_lines.append(f"Amount: {amount_line}")
    if download_link:
        text_lines.extend(["", "Download your MP3 here:", download_link])
    else:
        text_lines.extend(
            ["", "Your MP3 link will be sent separately if Drive is not configured for this track."]
        )
    text_lines.extend(
        [
            "",
            "Need help?",
            support_contact,
            "",
            "With gratitude,",
            "Michael — Music Acupuncture",
        ]
    )
    text = "\n".join(text_lines)

    if download_link:
        cta = f"""
              <p style="margin:22px 0 8px;text-align:center;">
                <a href="{_esc(download_link)}" style="display:inline-block;padding:14px 22px;border-radius:999px;background:{_GOLD};color:{_BG};text-decoration:none;font-weight:700;font-size:14px;">
                  Download your MP3
                </a>
              </p>
              <p style="margin:0 0 18px;text-align:center;font-size:12px;color:{_MUTED};word-break:break-all;">
                Or open: {_esc(download_link)}
              </p>"""
    else:
        cta = f"""
              <p style="margin:18px 0;padding:12px 14px;border-radius:10px;background:rgba(255,215,0,0.08);border:1px solid {_BORDER};color:{_MUTED};font-size:13px;">
                Your MP3 link will be sent separately if Drive is not configured for this track.
              </p>"""

    amount_row = _detail_row("Amount", amount_line) if amount_line else ""

    inner = f"""
              <p style="margin:16px 0 6px;font-size:18px;color:{_TEXT};">Dear {_esc(name)},</p>
              <p style="margin:0 0 18px;color:{_MUTED};">
                Thank you for supporting Music Acupuncture. Your healing sound is ready.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 8px;">
                {_detail_row("Track", title)}
                {amount_row}
              </table>
              {cta}
              <p style="margin:20px 0 0;color:{_MUTED};font-size:13px;">
                Need help? {_esc(support_contact)}
              </p>
              <p style="margin:18px 0 0;color:{_TEXT};">
                With gratitude,<br />
                <strong style="color:{_GOLD};">Michael</strong><br />
                <span style="color:{_MUTED};font-size:13px;">Music Acupuncture®</span>
              </p>"""

    html_body = _shell(
        title=subject,
        eyebrow="Purchase confirmation",
        inner_html=inner,
        footer_note="Listen daily for best results.",
    )
    return EmailContent(subject=subject, text=text, html=html_body)


def build_staff_email(
    *,
    track_title: str,
    buyer_label: str,
    buyer_email: str | None,
    amount: float,
    currency: str,
    purchased_at: str,
    source: str,
    download_link: str | None = None,
    recipient_role: str = "team",
) -> EmailContent:
    """
    Письмо владельцу / разработчику о новой покупке.
    recipient_role: 'owner' | 'developer' | 'team' — лёгкая персонализация заголовка.
    """
    title = (track_title or "Track").strip() or "Track"
    amount_s = format_money(amount, currency)
    src = (source or "website").strip() or "website"
    name = buyer_display_name(buyer_email=buyer_email, buyer_label=buyer_label)
    buyer_line = (buyer_label or "").strip() or "Unknown"
    if buyer_email and buyer_email not in buyer_line:
        buyer_line = f"{buyer_line} · {buyer_email}"

    role = (recipient_role or "team").strip().lower()
    if role == "owner":
        eyebrow = "New sale — shop owner"
    elif role == "developer":
        eyebrow = "New sale — developer notify"
    else:
        eyebrow = "New sale notification"

    subject = f"New purchase — {title}"

    text = "\n".join(
        [
            "New purchase on Music Acupuncture",
            "",
            f"Track: {title}",
            f"Buyer: {buyer_line}",
            f"Buyer name: {name}",
            f"Amount: {amount_s}",
            f"Date: {purchased_at}",
            f"Source: {src}",
            *(["", f"Download link: {download_link}"] if download_link else []),
        ]
    )

    dl_row = _detail_row("Download", download_link) if download_link else ""

    inner = f"""
              <p style="margin:16px 0 6px;font-size:18px;color:{_TEXT};">Hello,</p>
              <p style="margin:0 0 18px;color:{_MUTED};">
                A customer just completed a purchase. Details below.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                {_detail_row("Track", title)}
                {_detail_row("Buyer", buyer_line)}
                {_detail_row("Greeting name", name)}
                {_detail_row("Amount", amount_s)}
                {_detail_row("Date", purchased_at)}
                {_detail_row("Source", src)}
                {dl_row}
              </table>
              <p style="margin:22px 0 0;padding:12px 14px;border-radius:10px;background:rgba(255,215,0,0.08);border:1px solid {_BORDER};color:{_MUTED};font-size:13px;">
                Buyer email (Stripe): {_esc(buyer_email or "not provided")}
              </p>"""

    html_body = _shell(
        title=subject,
        eyebrow=eyebrow,
        inner_html=inner,
        footer_note="Internal notification — do not forward to customers.",
    )
    return EmailContent(subject=subject, text=text, html=html_body)


def build_startup_test_email(*, from_addr: str, api_url: str) -> EmailContent:
    """Краткое брендированное тестовое письмо при старте."""
    subject = "Music Acupuncture — email startup test (Resend)"
    text = (
        "This is an automatic test email from Music Acupuncture sell-bot.\n"
        "If you received it, Resend works:\n"
        f"  api={api_url}\n"
        f"  from={from_addr}\n"
    )
    inner = f"""
              <p style="margin:16px 0 10px;font-size:18px;color:{_TEXT};">Resend is connected</p>
              <p style="margin:0 0 14px;color:{_MUTED};">
                This is an automatic startup test from the Music Acupuncture sell-bot.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                {_detail_row("API", api_url)}
                {_detail_row("From", from_addr)}
              </table>"""
    html_body = _shell(
        title=subject,
        eyebrow="System check",
        inner_html=inner,
        footer_note="You can set EMAIL_STARTUP_TEST=0 to disable this message.",
    )
    return EmailContent(subject=subject, text=text, html=html_body)
