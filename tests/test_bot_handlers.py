from unittest.mock import AsyncMock, MagicMock

import pytest

from music_sales.bot_handlers import button, start

_SAMPLE_SONGS = {
    "s1": {"name": "Relaxing Sound", "price_usd": 16, "file": "SONGS/s1.mp3"},
    "s2": {"name": "Deep Sleep Track", "price_usd": 16, "file": "SONGS/s2.mp3"},
}


@pytest.mark.asyncio
async def test_start_replies_with_catalog_keyboard(mocker):
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=None)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    update.message.reply_text.assert_awaited_once()
    call = update.message.reply_text.call_args
    assert "Choose a track" in call[0][0]
    markup = call[1]["reply_markup"]
    assert len(markup.inline_keyboard) == 2


@pytest.mark.asyncio
async def test_button_requests_checkout_and_replies_with_url(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mock_post = mocker.patch("music_sales.bot_handlers.requests.post")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"url": "https://checkout.example/pay"}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    update = MagicMock()
    query = MagicMock()
    query.data = "s1"
    query.from_user.id = 999
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    await button(update, MagicMock(), backend_url="http://backend.test")

    mock_post.assert_called_once_with(
        "http://backend.test/create-checkout",
        json={"song_id": "s1", "telegram_id": 999},
        timeout=30,
    )
    query.message.reply_text.assert_awaited_once()
    sent = query.message.reply_text.call_args[0][0]
    assert "https://checkout.example/pay" in sent


@pytest.mark.asyncio
async def test_start_no_message_does_nothing():
    update = MagicMock()
    update.message = None
    await start(update, MagicMock())
    # no crash


@pytest.mark.asyncio
async def test_start_sends_owner_notification(mocker):
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=555)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    visitor = MagicMock()
    visitor.id = 111
    visitor.username = "buyer"
    visitor.first_name = "Ann"
    visitor.last_name = "Svensson"

    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = visitor

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await start(update, context)

    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args[1]["chat_id"] == 555
    assert "111" in context.bot.send_message.call_args[1]["text"]


@pytest.mark.asyncio
async def test_start_skips_notify_when_visitor_is_owner(mocker):
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=7846059164)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    visitor = MagicMock()
    visitor.id = 7846059164
    visitor.username = "mikael"
    visitor.first_name = "Mikael"
    visitor.last_name = None

    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = visitor

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await start(update, context)

    context.bot.send_message.assert_not_called()
