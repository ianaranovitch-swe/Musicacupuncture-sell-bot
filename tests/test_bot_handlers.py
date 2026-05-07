from unittest.mock import AsyncMock, MagicMock

import pytest

from music_sales.bot_handlers import help_command, start


@pytest.mark.asyncio
async def test_start_replies_with_config_hint_when_miniapp_not_set(mocker):
    mocker.patch("music_sales.bot_handlers.config.resolved_miniapp_url", return_value="")
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    context = MagicMock()

    await start(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "Music Store is not configured yet" in update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_start_sends_store_opener_only_when_miniapp_url_set(mocker):
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

    update.message.reply_text.assert_awaited_once()
    rt_kwargs = update.message.reply_text.call_args.kwargs
    assert "Music Store" in rt_kwargs["reply_markup"].inline_keyboard[0][0].text
    assert rt_kwargs["reply_markup"].inline_keyboard[0][0].web_app is not None


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
