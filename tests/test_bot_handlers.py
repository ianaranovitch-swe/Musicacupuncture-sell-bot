from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from music_sales.bot_handlers import _full_catalog_markup, button, gallery_callback, help_command, start

_SAMPLE_SONGS = {
    "s1": {"name": "Relaxing Sound", "price_usd": 16, "file": "songs/s1.mp3"},
    "s2": {"name": "Deep Sleep Track", "price_usd": 16, "file": "songs/s2.mp3"},
}
_SAMPLE_SONGS_8 = {
    f"s{i}": {"name": f"Track {i:02d}", "price_usd": 16, "file": f"songs/s{i}.mp3"}
    for i in range(1, 9)
}


@pytest.mark.asyncio
async def test_start_replies_with_config_hint_when_miniapp_not_set(mocker):
    mocker.patch("music_sales.bot_handlers.config.resolved_miniapp_url", return_value="")
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=None)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    send_card = mocker.patch("music_sales.bot_handlers._send_single_track_card", new_callable=AsyncMock)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat_id = 777
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    send_card.assert_not_called()
    update.message.reply_text.assert_awaited_once()
    assert "Music Store is not configured yet" in update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_start_sends_store_opener_only_when_miniapp_url_set(mocker):
    mocker.patch(
        "music_sales.bot_handlers.config.resolved_miniapp_url",
        return_value="https://user.github.io/repo/miniapp.html",
    )
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=None)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    send_card = mocker.patch("music_sales.bot_handlers._send_single_track_card", new_callable=AsyncMock)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat_id = 777
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    update.message.reply_text.assert_awaited_once()
    rt_kwargs = update.message.reply_text.call_args.kwargs
    assert "Music Store" in rt_kwargs["reply_markup"].inline_keyboard[0][0].text
    assert rt_kwargs["reply_markup"].inline_keyboard[0][0].web_app is not None
    send_card.assert_not_called()


@pytest.mark.asyncio
async def test_gallery_select_opens_track_card(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    send_card = mocker.patch("music_sales.bot_handlers._send_single_track_card", new_callable=AsyncMock)

    update = MagicMock()
    query = MagicMock()
    query.data = "g:s:000"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat.id = 777
    update.callback_query = query
    context = MagicMock()

    await gallery_callback(update, context)

    send_card.assert_awaited_once()
    kwargs = send_card.call_args.kwargs
    assert kwargs["chat_id"] == 777
    assert kwargs["song_idx"] == 0


@pytest.mark.asyncio
async def test_gallery_next_opens_next_track_card(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    send_card = mocker.patch("music_sales.bot_handlers._send_single_track_card", new_callable=AsyncMock)

    update = MagicMock()
    query = MagicMock()
    query.data = "g:n:001"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat.id = 888
    update.callback_query = query

    await gallery_callback(update, MagicMock())
    send_card.assert_awaited_once()
    kwargs = send_card.call_args.kwargs
    assert kwargs["chat_id"] == 888
    assert kwargs["song_idx"] == 1


def test_gallery_markup_shows_next_page_track_buttons_for_first_page():
    sorted_items = sorted(_SAMPLE_SONGS_8.items(), key=lambda kv: kv[1]["name"].lower())
    markup = _full_catalog_markup(sorted_items=sorted_items, current_idx=0, current_song_id="s1")
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "💳 Buy this track" in labels
    assert "🎵 Track 01" in labels
    assert "🎵 Track 08" in labels
    assert "NEXT" in labels


def test_full_catalog_markup_includes_music_store_when_miniapp_configured(mocker):
    mocker.patch("music_sales.bot_handlers.config.resolved_miniapp_url", return_value="https://app.example/miniapp.html")
    sorted_items = sorted(_SAMPLE_SONGS.items(), key=lambda kv: kv[1]["name"].lower())
    markup = _full_catalog_markup(sorted_items=sorted_items, current_idx=0, current_song_id="s1")
    first_row = markup.inline_keyboard[0]
    assert len(first_row) == 1
    assert first_row[0].text == "🎵 Open Music Store"
    assert first_row[0].web_app is not None
    assert first_row[0].web_app.url == "https://app.example/miniapp.html"


@pytest.mark.asyncio
async def test_button_first_click_shows_currency_buttons(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mock_post = mocker.patch("music_sales.bot_handlers.requests.post")

    update = MagicMock()
    query = MagicMock()
    query.data = "s1"
    query.from_user.id = 999
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    await button(update, MagicMock(), backend_url="http://backend.test")

    mock_post.assert_not_called()
    query.message.reply_text.assert_awaited_once()
    args = query.message.reply_text.call_args.args
    kwargs = query.message.reply_text.call_args.kwargs
    assert args[0] == "Choose your payment currency:"
    buttons = [btn.text for row in kwargs["reply_markup"].inline_keyboard for btn in row]
    assert buttons == ["USD", "EUR", "SEK"]


@pytest.mark.asyncio
async def test_button_currency_click_creates_checkout_and_replies_with_url(mocker):
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mock_post = mocker.patch("music_sales.bot_handlers.requests.post")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"url": "https://checkout.example/pay"}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    update = MagicMock()
    query = MagicMock()
    query.data = "pay:sek"
    query.from_user.id = 999
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {"pending_checkout_song_id": "s1"}

    await button(update, context, backend_url="http://backend.test")

    mock_post.assert_called_once_with(
        "http://backend.test/create-checkout",
        json={"song_id": "s1", "telegram_id": 999, "telegram_name": ANY, "currency": "sek"},
        timeout=30,
    )
    query.message.reply_text.assert_awaited_once()
    args = query.message.reply_text.call_args.args
    kwargs = query.message.reply_text.call_args.kwargs
    assert "Tap to open secure Stripe checkout:" in args[0]
    assert "https://checkout.example/pay" in args[0]
    assert "background" in args[0]
    markup = kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == "https://checkout.example/pay"


@pytest.mark.asyncio
async def test_help_command_shows_usage_and_quick_command_buttons():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    args = update.message.reply_text.call_args.args
    kwargs = update.message.reply_text.call_args.kwargs
    assert "/start" in args[0]
    assert "/buy" in args[0]
    assert "/help" in args[0]
    keyboard = kwargs["reply_markup"].keyboard
    labels = [btn.text for row in keyboard for btn in row]
    assert labels == ["/start", "/buy", "/help", "/health"]


@pytest.mark.asyncio
async def test_start_no_message_does_nothing():
    update = MagicMock()
    update.message = None
    await start(update, MagicMock())
    # no crash


@pytest.mark.asyncio
async def test_start_sends_owner_notification(mocker):
    mocker.patch("music_sales.bot_handlers.config.resolved_miniapp_url", return_value="")
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=555)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mocker.patch("music_sales.bot_handlers._send_single_track_card", new_callable=AsyncMock)
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
    assert "@buyer" in owner_calls[0].kwargs["text"]


@pytest.mark.asyncio
async def test_start_skips_notify_when_visitor_is_owner(mocker):
    mocker.patch("music_sales.bot_handlers.config.resolved_miniapp_url", return_value="")
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=7846059164)
    mocker.patch("music_sales.bot_handlers.discover_songs", return_value=_SAMPLE_SONGS)
    mocker.patch("music_sales.bot_handlers._send_single_track_card", new_callable=AsyncMock)
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
