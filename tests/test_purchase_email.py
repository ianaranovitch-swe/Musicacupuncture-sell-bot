"""Тесты писем после покупки (Gmail SMTP — мок)."""

from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from music_sales import purchase_email as pe


@pytest.fixture(autouse=True)
def _clear_purchase_email_env(monkeypatch):
    monkeypatch.delenv("ENABLE_PURCHASE_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)
    monkeypatch.delenv("SHOP_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("SUPPORT_CONTACT", raising=False)
    monkeypatch.delenv("SMTP_STARTUP_TEST", raising=False)


def test_purchase_emails_disabled_by_default():
    assert pe.purchase_emails_enabled() is False
    with patch.object(pe, "_send_smtp") as smtp:
        pe.send_purchase_emails(
            track_title="Heart",
            song_row={"name": "Divine sound Heart from God", "google_drive_file_id": "abc123"},
            amount=16.0,
            currency="USD",
            buyer_email="buyer@example.com",
            buyer_telegram_label="@buyer",
        )
        smtp.assert_not_called()


def test_send_purchase_emails_owner_and_buyer(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "app-pass")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner@gmail.com")
    monkeypatch.setenv("SUPPORT_CONTACT", "help@example.com")
    sent: list[tuple[str, str]] = []

    def _capture(*, to_addr: str, subject: str, body: str) -> None:
        sent.append((to_addr, subject))

    monkeypatch.setattr(pe, "_send_smtp", _capture)
    pe.send_purchase_emails(
        track_title="Divine sound Heart from God",
        song_row={"google_drive_file_id": "drive_id_99"},
        amount=16.0,
        currency="USD",
        buyer_email="buyer@example.com",
        buyer_telegram_label="@sarah",
        source="website",
    )
    assert len(sent) == 2
    assert sent[0][0] == "owner@gmail.com"
    assert "New purchase" in sent[0][1]
    assert sent[1][0] == "buyer@example.com"
    assert "Your purchase" in sent[1][1]


def test_send_purchase_emails_multiple_owners(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "app-pass")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner1@gmail.com, owner2@gmail.com")
    sent: list[str] = []

    def _capture(*, to_addr: str, subject: str, body: str) -> None:
        sent.append(to_addr)

    monkeypatch.setattr(pe, "_send_smtp", _capture)
    pe.send_purchase_emails(
        track_title="Heart",
        song_row={},
        amount=16.0,
        currency="USD",
        buyer_email="buyer@example.com",
        buyer_telegram_label="@sarah",
        source="website",
    )
    assert sent == ["owner1@gmail.com", "owner2@gmail.com", "buyer@example.com"]


def test_parse_email_addresses_comma_and_semicolon():
    assert pe._parse_email_addresses("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]
    assert pe._parse_email_addresses("a@x.com; b@y.com ; a@x.com") == ["a@x.com", "b@y.com"]
    assert pe._parse_email_addresses("not-an-email, ok@ok.com") == ["ok@ok.com"]


def test_shop_owner_emails_from_env(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "fallback@gmail.com")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "one@gmail.com, two@gmail.com")
    assert pe._shop_owner_emails() == ["one@gmail.com", "two@gmail.com"]
    assert pe._shop_owner_email() == "one@gmail.com, two@gmail.com"


def test_startup_test_sends_to_all_owners(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "secret")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "a@gmail.com; b@gmail.com")
    monkeypatch.setenv("SMTP_STARTUP_TEST", "1")
    with patch.object(pe, "_send_smtp") as smtp:
        assert pe.send_smtp_startup_test_email() is True
        assert smtp.call_count == 2
        assert smtp.call_args_list[0].kwargs["to_addr"] == "a@gmail.com"
        assert smtp.call_args_list[1].kwargs["to_addr"] == "b@gmail.com"


def test_send_purchase_emails_skips_buyer_without_email(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "app-pass")
    sent: list[str] = []

    def _capture(*, to_addr: str, subject: str, body: str) -> None:
        sent.append(to_addr)

    monkeypatch.setattr(pe, "_send_smtp", _capture)
    pe.send_purchase_emails(
        track_title="Track",
        song_row={},
        amount=1.0,
        currency="USD",
        buyer_email=None,
        buyer_telegram_label="Telegram user id 123",
    )
    assert sent == ["shop@gmail.com"]


def test_drive_download_link_from_song_row():
    link = pe.drive_download_link({"google_drive_file_id": "1AbC"})
    assert link == "https://drive.google.com/file/d/1AbC/view"


def test_drive_download_link_missing_id():
    assert pe.drive_download_link({}) is None


def test_buyer_email_from_checkout_session():
    session = {
        "customer_details": {"email": "stripe@buyer.com"},
        "amount_total": 1600,
        "currency": "usd",
    }
    assert pe.buyer_email_from_checkout_session(session) == "stripe@buyer.com"


def test_buyer_label_from_metadata_username():
    assert pe.buyer_label_from_metadata("sarah_m", 1) == "@sarah_m"


def test_send_purchase_emails_for_stripe_session(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "x")
    calls: list[str] = []
    monkeypatch.setattr(
        pe,
        "send_purchase_emails",
        lambda **kw: calls.append(kw.get("buyer_email") or ""),
    )
    pe.send_purchase_emails_for_stripe_session(
        {
            "amount_total": 16900,
            "currency": "sek",
            "customer_email": "web@example.com",
        },
        catalog={"heart": {"name": "Divine sound Heart from God", "google_drive_file_id": "x"}},
        song_id="heart",
        meta={"source": "website", "telegram_name": "Website customer"},
        telegram_id_int=0,
    )
    assert calls == ["web@example.com"]


def test_smtp_uses_starttls(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "secret")
    mock_smtp = MagicMock()
    with patch("music_sales.purchase_email.smtplib.SMTP", return_value=mock_smtp) as smtp_ctor:
        pe._send_smtp(to_addr="a@b.com", subject="S", body="B")
    smtp_ctor.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
    mock_smtp.ehlo.assert_called()
    mock_smtp.starttls.assert_called_once()
    method_names = [name for name, _args, _kwargs in mock_smtp.method_calls]
    assert method_names.index("starttls") < method_names.index("login")
    mock_smtp.login.assert_called_once_with("shop@gmail.com", "secret")
    mock_smtp.send_message.assert_called_once()
    mock_smtp.quit.assert_called_once()


def test_gmail_password_strips_spaces(monkeypatch):
    monkeypatch.setenv("GMAIL_PASSWORD", "abcd efgh ijkl mnop")
    assert pe._gmail_password() == "abcdefghijklmnop"


def test_startup_test_sends_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_STARTUP_TEST", "1")
    with patch.object(pe, "_send_smtp") as smtp:
        assert pe.send_smtp_startup_test_email() is True
        smtp.assert_called_once()
        assert smtp.call_args.kwargs["to_addr"] == "shop@gmail.com"
        assert "SMTP startup test" in smtp.call_args.kwargs["subject"]


def test_startup_test_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "0")
    with patch.object(pe, "_send_smtp") as smtp:
        assert pe.send_smtp_startup_test_email() is False
        smtp.assert_not_called()


def test_smtp_logs_authentication_error(monkeypatch, caplog):
    monkeypatch.setenv("GMAIL_USER", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "bad")
    mock_smtp = MagicMock()
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")
    with patch("music_sales.purchase_email.smtplib.SMTP", return_value=mock_smtp):
        with caplog.at_level("ERROR"):
            with pytest.raises(smtplib.SMTPAuthenticationError):
                pe._send_smtp(to_addr="a@b.com", subject="S", body="B")
    assert any("Gmail SMTP failed" in r.message for r in caplog.records)
    assert any("stage=login" in r.message for r in caplog.records)