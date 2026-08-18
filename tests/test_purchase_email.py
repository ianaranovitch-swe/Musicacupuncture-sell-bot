"""Тесты писем после покупки (Resend API — мок)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from music_sales import purchase_email as pe


@pytest.fixture(autouse=True)
def _clear_purchase_email_env(monkeypatch):
    monkeypatch.delenv("ENABLE_PURCHASE_EMAIL", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)
    monkeypatch.delenv("SHOP_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("DEVELOPER_EMAIL", raising=False)
    monkeypatch.delenv("SUPPORT_CONTACT", raising=False)
    monkeypatch.delenv("EMAIL_STARTUP_TEST", raising=False)
    monkeypatch.delenv("SMTP_STARTUP_TEST", raising=False)
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)


def test_purchase_emails_disabled_by_default():
    assert pe.purchase_emails_enabled() is False
    with patch.object(pe, "_send_email") as send:
        pe.send_purchase_emails(
            track_title="Heart",
            song_row={"name": "Divine sound Heart from God", "google_drive_file_id": "abc123"},
            amount=16.0,
            currency="USD",
            buyer_email="buyer@example.com",
            buyer_telegram_label="@buyer",
        )
        send.assert_not_called()


def test_send_purchase_emails_owner_developer_and_buyer(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM", "Music Acupuncture <orders@example.com>")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner@gmail.com")
    monkeypatch.setenv("DEVELOPER_EMAIL", "dev@example.com")
    monkeypatch.setenv("SUPPORT_CONTACT", "help@example.com")
    sent: list[tuple[str, str]] = []

    def _capture(*, to_addr: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append((to_addr, subject))
        assert html and "#1a0533" in html

    monkeypatch.setattr(pe, "_send_email", _capture)
    pe.send_purchase_emails(
        track_title="Divine sound Heart from God",
        song_row={"google_drive_file_id": "drive_id_99"},
        amount=16.0,
        currency="USD",
        buyer_email="buyer@example.com",
        buyer_telegram_label="@sarah",
        source="website",
    )
    assert len(sent) == 3
    assert sent[0][0] == "owner@gmail.com"
    assert "New purchase" in sent[0][1]
    assert sent[1][0] == "dev@example.com"
    assert sent[2][0] == "buyer@example.com"
    assert "Your purchase" in sent[2][1]


def test_send_purchase_emails_dedupes_owner_and_developer(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "same@example.com")
    monkeypatch.setenv("DEVELOPER_EMAIL", "same@example.com")
    sent: list[str] = []

    def _capture(*, to_addr: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append(to_addr)

    monkeypatch.setattr(pe, "_send_email", _capture)
    pe.send_purchase_emails(
        track_title="Heart",
        song_row={},
        amount=16.0,
        currency="USD",
        buyer_email="buyer@example.com",
        source="website",
    )
    assert sent == ["same@example.com", "buyer@example.com"]


def test_send_purchase_emails_multiple_owners(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner1@gmail.com, owner2@gmail.com")
    sent: list[str] = []

    def _capture(*, to_addr: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append(to_addr)

    monkeypatch.setattr(pe, "_send_email", _capture)
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
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "one@gmail.com, two@gmail.com")
    assert pe._shop_owner_emails() == ["one@gmail.com", "two@gmail.com"]
    assert pe._shop_owner_email() == "one@gmail.com, two@gmail.com"


def test_startup_test_sends_to_all_staff(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "a@gmail.com")
    monkeypatch.setenv("DEVELOPER_EMAIL", "b@gmail.com")
    monkeypatch.setenv("EMAIL_STARTUP_TEST", "1")
    with patch.object(pe, "_send_email") as send:
        assert pe.send_email_startup_test() is True
        assert send.call_count == 2
        assert send.call_args_list[0].kwargs["to_addr"] == "a@gmail.com"
        assert send.call_args_list[1].kwargs["to_addr"] == "b@gmail.com"


def test_send_purchase_emails_skips_buyer_without_email(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner@example.com")
    sent: list[str] = []

    def _capture(*, to_addr: str, subject: str, body: str, html: str | None = None) -> None:
        sent.append(to_addr)

    monkeypatch.setattr(pe, "_send_email", _capture)
    pe.send_purchase_emails(
        track_title="Track",
        song_row={},
        amount=1.0,
        currency="USD",
        buyer_email=None,
        buyer_telegram_label="Telegram user id 123",
    )
    assert sent == ["owner@example.com"]


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
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
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


def test_resend_send_posts_json(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_secret")
    monkeypatch.setenv("RESEND_FROM", "Shop <orders@example.com>")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "email_123"}
    with patch("music_sales.purchase_email.requests.post", return_value=mock_resp) as post:
        pe._send_email(to_addr="a@b.com", subject="S", body="B", html="<p>Hi</p>")
    post.assert_called_once()
    kwargs = post.call_args.kwargs
    assert kwargs["json"]["from"] == "Shop <orders@example.com>"
    assert kwargs["json"]["to"] == ["a@b.com"]
    assert kwargs["json"]["subject"] == "S"
    assert kwargs["json"]["text"] == "B"
    assert kwargs["json"]["html"] == "<p>Hi</p>"
    assert kwargs["headers"]["Authorization"] == "Bearer re_secret"


def test_startup_test_sends_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("EMAIL_STARTUP_TEST", "1")
    with patch.object(pe, "_send_email") as send:
        assert pe.send_smtp_startup_test_email() is True
        send.assert_called_once()
        assert send.call_args.kwargs["to_addr"] == "owner@example.com"
        assert "startup test" in send.call_args.kwargs["subject"].lower()


def test_startup_test_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PURCHASE_EMAIL", "0")
    with patch.object(pe, "_send_email") as send:
        assert pe.send_email_startup_test() is False
        send.assert_not_called()


def test_resend_logs_http_error(monkeypatch, caplog):
    monkeypatch.setenv("RESEND_API_KEY", "re_bad")
    monkeypatch.setenv("RESEND_FROM", "orders@example.com")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = '{"message":"Invalid API key"}'
    mock_resp.raise_for_status.side_effect = requests.HTTPError("401", response=mock_resp)
    with patch("music_sales.purchase_email.requests.post", return_value=mock_resp):
        with caplog.at_level("ERROR"):
            with pytest.raises(requests.HTTPError):
                pe._send_email(to_addr="a@b.com", subject="S", body="B")
    assert any("Resend" in r.message for r in caplog.records)
