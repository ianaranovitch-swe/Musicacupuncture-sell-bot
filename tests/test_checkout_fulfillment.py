"""Тесты идемпотентной обработки checkout.session.completed."""

from unittest.mock import MagicMock

import pytest

_TEST_CATALOG = {
    "song1": {"name": "Relaxing Sound", "price_usd": 16, "file": "songs/song1.mp3"},
}


def test_sale_event_exists_for_session(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_LOG_JSON", "[]")
    from music_sales.sales_log import append_sale_event, sale_event_exists_for_session

    assert sale_event_exists_for_session("cs_abc") is False
    append_sale_event(
        song_id="song1",
        track_title="Relaxing Sound",
        session_id="cs_abc",
        source="website",
    )
    assert sale_event_exists_for_session("cs_abc") is True
    assert sale_event_exists_for_session("cs_other") is False


def test_fulfill_website_checkout_once(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_LOG_JSON", "[]")
    mock_email = mocker.patch("music_sales.checkout_fulfillment.send_purchase_emails_for_stripe_session")
    mock_notify = mocker.patch("music_sales.checkout_fulfillment.notify_owner_http")

    from music_sales.checkout_fulfillment import fulfill_checkout_session_completed

    session = {
        "id": "cs_live_1",
        "payment_status": "paid",
        "amount_total": 1600,
        "currency": "usd",
        "metadata": {
            "telegram_id": "0",
            "telegram_name": "Website customer",
            "song_id": "song1",
            "source": "website",
        },
    }

    assert fulfill_checkout_session_completed(session, catalog=_TEST_CATALOG) is True
    mock_email.assert_called_once()
    mock_notify.assert_called_once()

    mock_email.reset_mock()
    mock_notify.reset_mock()

    assert fulfill_checkout_session_completed(session, catalog=_TEST_CATALOG) is False
    mock_email.assert_not_called()
    mock_notify.assert_not_called()


def test_fulfill_website_without_telegram_id_but_source_website(mocker, monkeypatch):
    """Покупка с сайта: telegram_id может быть пустым, если source=website."""
    monkeypatch.setenv("SALES_LOG_JSON", "[]")
    mocker.patch("music_sales.checkout_fulfillment.append_sale_event")
    mocker.patch("music_sales.checkout_fulfillment.send_purchase_emails_for_stripe_session")
    mock_notify = mocker.patch("music_sales.checkout_fulfillment.notify_owner_http")

    from music_sales.checkout_fulfillment import fulfill_checkout_session_completed

    session = {
        "id": "cs_live_2",
        "metadata": {
            "song_id": "song1",
            "source": "website",
            "telegram_name": "Website customer",
        },
    }
    assert fulfill_checkout_session_completed(session, catalog=_TEST_CATALOG) is True
    mock_notify.assert_called_once()


def test_fulfill_notify_failure_does_not_raise(mocker, monkeypatch):
    """Сбой Telegram-уведомления не роняет fulfillment (webhook должен вернуть 200)."""
    monkeypatch.setenv("SALES_LOG_JSON", "[]")
    mocker.patch("music_sales.checkout_fulfillment.send_purchase_emails_for_stripe_session")
    mocker.patch(
        "music_sales.checkout_fulfillment.notify_owner_http",
        side_effect=RuntimeError("telegram down"),
    )

    from music_sales.checkout_fulfillment import fulfill_checkout_session_completed

    session = {
        "id": "cs_notify_fail",
        "metadata": {
            "telegram_id": "0",
            "song_id": "song1",
            "source": "website",
        },
    }
    assert fulfill_checkout_session_completed(session, catalog=_TEST_CATALOG) is True
