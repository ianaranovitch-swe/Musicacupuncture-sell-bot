import pytest


def test_build_application_requires_bot_token(mocker):
    mocker.patch("music_sales.bot_app.config.BOT_TOKEN", "")
    from music_sales.bot_app import build_application

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        build_application()
