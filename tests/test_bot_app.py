import pytest

from music_sales.bot_app import _log_webhook_preflight


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


def test_build_application_requires_bot_token(mocker):
    mocker.patch("music_sales.bot_app.config.BOT_TOKEN", "")
    from music_sales.bot_app import build_application

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        build_application()
