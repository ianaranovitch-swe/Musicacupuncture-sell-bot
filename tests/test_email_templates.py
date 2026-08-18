"""Тесты брендированных HTML-шаблонов писем."""

from __future__ import annotations

from music_sales.email_templates import (
    buyer_display_name,
    build_buyer_email,
    build_staff_email,
    build_startup_test_email,
    format_money,
)


def test_format_money_usd_sek_eur():
    assert format_money(16, "USD") == "$16.00"
    assert format_money(169, "sek") == "169.00 kr"
    assert format_money(10, "EUR") == "€10.00"


def test_buyer_display_name_from_telegram_and_email():
    assert buyer_display_name(buyer_email=None, buyer_label="@sarah_m") == "Sarah M"
    assert (
        buyer_display_name(buyer_email="alex@example.com", buyer_label="Unknown") == "Alex"
    )
    assert buyer_display_name(buyer_email=None, buyer_label="Unknown") == "Friend"


def test_build_buyer_email_personalized_html():
    content = build_buyer_email(
        track_title="Divine sound Heart from God",
        download_link="https://drive.google.com/file/d/abc/view",
        buyer_email="buyer@example.com",
        buyer_label="@sarah",
        amount=16.0,
        currency="USD",
        support_contact="help@example.com",
    )
    assert "Your purchase" in content.subject
    assert "Dear Sarah" in content.text
    assert "Download your MP3 here:" in content.text
    assert "Dear Sarah" in content.html
    assert "Download your MP3" in content.html
    assert "#ffd700" in content.html
    assert "#1a0533" in content.html
    assert "drive.google.com" in content.html


def test_build_staff_email_role_eyebrow():
    owner = build_staff_email(
        track_title="Heart",
        buyer_label="@sarah",
        buyer_email="buyer@example.com",
        amount=16.0,
        currency="USD",
        purchased_at="2026-08-12 10:00 UTC",
        source="website",
        recipient_role="owner",
    )
    assert "New purchase" in owner.subject
    assert "shop owner" in owner.html
    assert "buyer@example.com" in owner.html

    developer = build_staff_email(
        track_title="Heart",
        buyer_label="@sarah",
        buyer_email="buyer@example.com",
        amount=16.0,
        currency="USD",
        purchased_at="2026-08-12 10:00 UTC",
        source="telegram",
        recipient_role="developer",
    )
    assert "developer notify" in developer.html


def test_build_startup_test_email():
    content = build_startup_test_email(
        from_addr="orders@example.com",
        api_url="https://api.resend.com/emails",
    )
    assert "startup test" in content.subject.lower()
    assert "Resend is connected" in content.html
    assert "orders@example.com" in content.text
