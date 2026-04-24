from unittest.mock import AsyncMock, MagicMock

import pytest

from music_sales.bot_handlers import button, gallery_callback, start

_SAMPLE_SONGS = {
    "s1": {"name": "Relaxing Sound", "price_usd": 16, "file": "songs/s1.mp3"},
    "s2": {"name": "Deep Sleep Track", "price_usd": 16, "file": "songs/s2.mp3"},
}


@pytest.mark.asyncio
async def test_start_replies_with_catalog_keyboard(mocker):
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=None)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    send_gallery = mocker.patch("music_sales.bot_handlers._send_gallery_page_cards_to_chat", new_callable=AsyncMock)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat_id = 777
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    send_gallery.assert_awaited_once()
    kwargs = send_gallery.call_args.kwargs
    assert kwargs["chat_id"] == 777
    assert kwargs["page"] == 0


@pytest.mark.asyncio
async def test_gallery_select_opens_track_card(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mocker.patch("music_sales.bot_handlers._cover_path_for_song", return_value=None)
    mocker.patch("music_sales.bot_handlers._load_tracks_from_tracks_py", return_value=[])
    send_controls = mocker.patch("music_sales.bot_handlers._send_gallery_controls_for_page", new_callable=AsyncMock)

    update = MagicMock()
    query = MagicMock()
    query.data = "g:s:000"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query
    context = MagicMock()

    await gallery_callback(update, context)

    query.message.reply_text.assert_awaited_once()
    sent = query.message.reply_text.await_args_list[0].args[0]
    assert "Deep Sleep Track" in sent
    send_controls.assert_awaited_once()


@pytest.mark.asyncio
async def test_gallery_select_includes_description_from_tracks_py(mocker):
    """Описание подтягивается из `tracks.py` по stem (каталог songs/*.mp3 и поле audio)."""
    tracks_stub = [
        {
            "id": 1,
            "title": "Deep Sleep Track",
            "description": "First line of story.\nSecond line.",
            "audio": "songs/s2.mp3",
        }
    ]
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mocker.patch("music_sales.bot_handlers._load_tracks_from_tracks_py", return_value=tracks_stub)
    mocker.patch("music_sales.bot_handlers._cover_path_for_song", return_value=None)
    mocker.patch("music_sales.bot_handlers._send_gallery_controls_for_page", new_callable=AsyncMock)

    update = MagicMock()
    query = MagicMock()
    query.data = "g:s:000"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    await gallery_callback(update, MagicMock())

    sent = query.message.reply_text.await_args_list[0].args[0]
    assert "Deep Sleep Track" in sent
    assert "First line of story." in sent
    assert "Second line." in sent


@pytest.mark.asyncio
async def test_gallery_page_sends_controls_message(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    send_controls = mocker.patch("music_sales.bot_handlers._send_gallery_controls_for_page", new_callable=AsyncMock)

    update = MagicMock()
    query = MagicMock()
    query.data = "g:p:000"
    query.answer = AsyncMock()
    query.message = MagicMock()
    update.callback_query = query

    context = MagicMock()
    await gallery_callback(update, context)

    send_controls.assert_awaited_once()


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
    mocker.patch("music_sales.bot_handlers._send_gallery_page_cards_to_chat", new_callable=AsyncMock)
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

    owner_calls = [c for c in context.bot.send_message.await_args_list if c.kwargs.get("chat_id") == 555]
    assert len(owner_calls) == 1
    assert "111" in owner_calls[0].kwargs["text"]


@pytest.mark.asyncio
async def test_start_skips_notify_when_visitor_is_owner(mocker):
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=7846059164)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mocker.patch("music_sales.bot_handlers._send_gallery_page_cards_to_chat", new_callable=AsyncMock)
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

    owner_calls = [c for c in context.bot.send_message.await_args_list if c.kwargs.get("chat_id") == 7846059164]
    assert len(owner_calls) == 0
