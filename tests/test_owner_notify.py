"""Уведомления владельцу и разработчику."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from music_sales.owner_notify import notify_owner_async, owner_and_developer_chat_ids


def test_owner_and_developer_chat_ids_dedupes(mocker):
    mocker.patch("music_sales.owner_notify.config.owner_telegram_id_int", return_value=111)
    mocker.patch("music_sales.owner_notify.config.developer_telegram_id_int", return_value=222)
    assert owner_and_developer_chat_ids() == [111, 222]


def test_owner_and_developer_same_id_no_duplicate(mocker):
    mocker.patch("music_sales.owner_notify.config.owner_telegram_id_int", return_value=111)
    mocker.patch("music_sales.owner_notify.config.developer_telegram_id_int", return_value=111)
    assert owner_and_developer_chat_ids() == [111]


def test_skip_actor_id(mocker):
    mocker.patch("music_sales.owner_notify.config.owner_telegram_id_int", return_value=111)
    mocker.patch("music_sales.owner_notify.config.developer_telegram_id_int", return_value=222)
    assert owner_and_developer_chat_ids(skip_telegram_user_id=222) == [111]


@pytest.mark.asyncio
async def test_notify_owner_async_sends_to_developer(mocker):
    mocker.patch("music_sales.owner_notify.config.owner_telegram_id_int", return_value=555)
    mocker.patch("music_sales.owner_notify.config.developer_telegram_id_int", return_value=999)
    visitor = MagicMock()
    visitor.id = 111
    visitor.username = "guest"
    visitor.first_name = "Guest"
    visitor.last_name = None

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    from music_sales.owner_notify import notify_owner_async

    await notify_owner_async(context, actor=visitor, event="Bot started")

    chat_ids = [c.kwargs.get("chat_id") for c in context.bot.send_message.await_args_list]
    assert 555 in chat_ids
    assert 999 in chat_ids
