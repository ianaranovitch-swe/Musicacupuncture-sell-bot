import asyncio

import pytest

from music_sales.bot_app import _error_handler, _log_webhook_preflight
from telegram.error import Conflict


def test_log_webhook_preflight_empty_token():
    _log_webhook_preflight("")  # не падает, не ходит в сеть


def test_log_webhook_preflight_network_error(mocker):
    mocker.patch("music_sales.bot_app.requests.get", side_effect=OSError("boom"))
    _log_webhook_preflight("123:abc")  # только warning в лог, без исключения


def test_log_worker_identity_does_not_raise():
    from music_sales.bot_app import _log_worker_identity

    _log_worker_identity()


def test_delay_before_polling_skips_when_unset(mocker, monkeypatch):
    monkeypatch.delenv("BOT_POLLING_START_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    sleep = mocker.patch("music_sales.bot_app.time.sleep")
    from music_sales.bot_app import _delay_before_polling_if_configured

    _delay_before_polling_if_configured()
    sleep.assert_not_called()


def test_delay_before_polling_railway_default_when_no_explicit_var(mocker, monkeypatch):
    monkeypatch.delenv("BOT_POLLING_START_DELAY_SECONDS", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-env-id")
    sleep = mocker.patch("music_sales.bot_app.time.sleep")
    from music_sales.bot_app import _delay_before_polling_if_configured

    _delay_before_polling_if_configured()
    sleep.assert_called_once_with(18.0)


def test_delay_before_polling_explicit_zero_disables_even_on_railway(mocker, monkeypatch):
    monkeypatch.setenv("BOT_POLLING_START_DELAY_SECONDS", "0")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-env-id")
    sleep = mocker.patch("music_sales.bot_app.time.sleep")
    from music_sales.bot_app import _delay_before_polling_if_configured

    _delay_before_polling_if_configured()
    sleep.assert_not_called()


def test_delay_before_polling_calls_sleep_when_positive(mocker, monkeypatch):
    monkeypatch.setenv("BOT_POLLING_START_DELAY_SECONDS", "2.5")
    sleep = mocker.patch("music_sales.bot_app.time.sleep")
    from music_sales.bot_app import _delay_before_polling_if_configured

    _delay_before_polling_if_configured()
    sleep.assert_called_once_with(2.5)


def test_bootstrap_retries_default_and_invalid(monkeypatch, mocker):
    monkeypatch.delenv("BOT_POLLING_BOOTSTRAP_RETRIES", raising=False)
    from music_sales.bot_app import _bootstrap_retries_for_polling

    assert _bootstrap_retries_for_polling() == 10
    monkeypatch.setenv("BOT_POLLING_BOOTSTRAP_RETRIES", "3")
    assert _bootstrap_retries_for_polling() == 3
    monkeypatch.setenv("BOT_POLLING_BOOTSTRAP_RETRIES", "nope")
    mocker.patch("music_sales.bot_app.logger.warning")
    assert _bootstrap_retries_for_polling() == 10


def test_error_handler_conflict_does_not_log_exc_info(mocker):
    from unittest.mock import MagicMock

    log_warning = mocker.patch("music_sales.bot_app.logger.warning")
    ctx = MagicMock()
    ctx.error = Conflict("Conflict: terminated by other getUpdates request")
    asyncio.run(_error_handler(None, ctx))
    log_warning.assert_called_once()
    assert "getUpdates Conflict" in log_warning.call_args[0][0]


def test_build_application_requires_bot_token(mocker):
    mocker.patch("music_sales.bot_app.config.BOT_TOKEN", "")
    from music_sales.bot_app import build_application

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        build_application()
