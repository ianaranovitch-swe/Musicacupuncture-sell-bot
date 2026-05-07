from unittest.mock import AsyncMock, MagicMock

import pytest

from music_sales.bot_handlers import FREE_TRACK_CB, FREE_TRACK_TITLE, help_command, send_free_track, start


@pytest.mark.asyncio
async def test_start_replies_with_config_hint_when_miniapp_not_set(mocker):
    mocker.patch("music_sales.bot_handlers.config.resolved_miniapp_url", return_value="")
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=None)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    assert update.message.reply_text.await_count == 2
    second = update.message.reply_text.await_args_list[1]
    assert "Music Store is not configured yet" in (second.args[0] or "")


@pytest.mark.asyncio
async def test_start_sends_store_opener_only_when_miniapp_url_set(mocker):
    mocker.patch(
        "music_sales.bot_handlers.config.resolved_miniapp_url",
        return_value="https://user.github.io/repo/miniapp.html",
    )
    mocker.patch("music_sales.bot_handlers.config.owner_telegram_id_int", return_value=None)
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    assert update.message.reply_text.await_count == 2
    second = update.message.reply_text.await_args_list[1]
    rt_kwargs = second.kwargs
    assert "Music Store" in rt_kwargs["reply_markup"].inline_keyboard[0][0].text
    assert rt_kwargs["reply_markup"].inline_keyboard[0][0].web_app is not None
    assert "menu button" in (second.args[0] or "").lower()


@pytest.mark.asyncio
async def test_start_shows_free_gift_button_first(mocker):
    mocker.patch(
        "music_sales.bot_handlers.config.resolved_miniapp_url",
        return_value="https://user.github.io/repo/miniapp.html",
    )
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    # Первый reply_text — подарок, в нём есть кнопка
    first_call = update.message.reply_text.await_args_list[0]
    markup = first_call.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == FREE_TRACK_CB
    assert FREE_TRACK_TITLE in (first_call.args[0] or "")


@pytest.mark.asyncio
async def test_send_free_track_uses_file_id_and_sends_document(mocker):
    mocker.patch(
        "music_sales.bot_handlers.load_file_ids_dict",
        return_value={FREE_TRACK_TITLE: "doc_file_id_123"},
    )
    mocker.patch("music_sales.bot_handlers.Path.is_file", return_value=False)
    update = MagicMock()
    q = MagicMock()
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.chat_id = 777
    update.callback_query = q
    update.effective_chat = MagicMock()
    update.effective_chat.id = 777
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await send_free_track(update, context)

    context.bot.send_document.assert_awaited_once()
    kwargs = context.bot.send_document.call_args.kwargs
    assert kwargs["chat_id"] == 777
    assert kwargs["document"] == "doc_file_id_123"


@pytest.mark.asyncio
async def test_help_command_shows_usage_and_quick_command_buttons():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    args = update.message.reply_text.call_args.args
    assert "/start" in args[0]
    assert "/help" in args[0]
    assert "/buy" not in args[0]


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
