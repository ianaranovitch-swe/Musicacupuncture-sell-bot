import pytest

from music_sales.bot_app import _log_webhook_preflight


def test_log_webhook_preflight_empty_token():
    _log_webhook_preflight("")  # не падает, не ходит в сеть


def test_log_webhook_preflight_network_error(mocker):
    mocker.patch("music_sales.bot_app.requests.get", side_effect=OSError("boom"))
    _log_webhook_preflight("123:abc")  # только warning в лог, без исключения


def test_build_application_requires_bot_token(mocker):
    mocker.patch("music_sales.bot_app.config.BOT_TOKEN", "")
    from music_sales.bot_app import build_application

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        build_application()
