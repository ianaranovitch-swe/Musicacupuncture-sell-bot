from unittest.mock import AsyncMock, MagicMock

import pytest

from music_sales.bot_handlers import (
    ABOUT_MICHAEL_CB,
    ABOUT_MICHAEL_BUTTON_TEXT,
    FREE_TRACK_CB,
    FREE_TRACK_TITLE,
    help_command,
    send_free_track,
    start,
)
from music_sales.testimonials_bot import REVIEWS_OPEN_CB


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

    assert update.message.reply_text.await_count == 3
    last = update.message.reply_text.await_args_list[-1]
    assert "Music Store is not configured yet" in (last.args[0] or "")


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

    assert update.message.reply_text.await_count == 3
    store_msg = update.message.reply_text.await_args_list[-1]
    rt_kwargs = store_msg.kwargs
    assert "Music Store" in rt_kwargs["reply_markup"].inline_keyboard[0][0].text
    assert rt_kwargs["reply_markup"].inline_keyboard[0][0].web_app is not None
    assert "menu button" in (store_msg.args[0] or "").lower()


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
    assert markup.inline_keyboard[1][0].text == "⭐ Customer Reviews"
    assert markup.inline_keyboard[2][0].callback_data == ABOUT_MICHAEL_CB
    assert markup.inline_keyboard[2][0].text == ABOUT_MICHAEL_BUTTON_TEXT
    assert markup.inline_keyboard[2][0].url is None
    assert FREE_TRACK_TITLE in (first_call.args[0] or "")


@pytest.mark.asyncio
async def test_send_about_michael_callback_sends_video_photos_and_body(mocker, tmp_path):
    photo = tmp_path / "assets" / "about-michael.png"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"png")
    video = tmp_path / "assets" / "michael.mp4"
    video.write_bytes(b"mp4")
    mocker.patch("music_sales.bot_handlers._repo_root", return_value=tmp_path)
    mocker.patch(
        "music_sales.bot_handlers.existing_about_michael_photos",
        return_value=[photo],
    )
    mocker.patch(
        "music_sales.bot_handlers.existing_about_michael_video",
        return_value=video,
    )
    update = MagicMock()
    q = MagicMock()
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.chat_id = 42
    update.callback_query = q
    update.message = None
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.send_animation = AsyncMock()
    context.bot.send_media_group = AsyncMock()
    context.bot.get_me = AsyncMock(return_value=MagicMock(username="music_bot"))
    mocker.patch(
        "music_sales.bot_handlers.config.resolved_miniapp_url",
        return_value="https://example.com/miniapp.html",
    )

    from music_sales.bot_handlers import ABOUT_VIDEO_SOUND_CB, send_about_michael

    await send_about_michael(update, context)

    q.answer.assert_awaited_once()
    context.bot.send_animation.assert_awaited_once()
    assert "reply_markup" not in context.bot.send_animation.call_args.kwargs
    sound_btn_calls = [
        c
        for c in context.bot.send_message.await_args_list
        if c.kwargs.get("reply_markup") is not None
    ]
    assert len(sound_btn_calls) >= 1
    first_btn = sound_btn_calls[0].kwargs["reply_markup"].inline_keyboard[0][0]
    assert first_btn.callback_data == ABOUT_VIDEO_SOUND_CB or (
        first_btn.url and "michael.mp4" in (first_btn.url or "")
    )
    reply_used = any(c.kwargs.get("reply_parameters") is not None for c in context.bot.send_message.await_args_list)
    assert reply_used
    context.bot.send_photo.assert_awaited_once()
    footer_call = context.bot.send_message.await_args_list[-1]
    assert "Browse the Music Store" in footer_call.kwargs["text"]
    assert footer_call.kwargs.get("reply_parameters") is None
    nav_kb = footer_call.kwargs["reply_markup"].inline_keyboard
    assert nav_kb[0][0].callback_data == REVIEWS_OPEN_CB
    assert nav_kb[1][0].web_app is not None
    assert "Open Music Store" in nav_kb[1][0].text
    bio_calls = [
        c for c in context.bot.send_message.await_args_list if "Michael B. Johnsson" in (c.kwargs.get("text") or "")
    ]
    assert len(bio_calls) == 1


@pytest.mark.asyncio
async def test_about_video_sound_callback_sends_video(mocker, tmp_path):
    video = tmp_path / "assets" / "michael.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")
    mocker.patch("music_sales.bot_handlers._repo_root", return_value=tmp_path)
    mocker.patch(
        "music_sales.bot_handlers.existing_about_michael_video",
        return_value=video,
    )
    update = MagicMock()
    q = MagicMock()
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.chat_id = 99
    update.callback_query = q
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_video = AsyncMock()
    context.bot.get_me = AsyncMock(return_value=MagicMock(username="music_bot"))
    mocker.patch(
        "music_sales.bot_handlers.config.resolved_miniapp_url",
        return_value="https://example.com/miniapp.html",
    )

    from music_sales.bot_handlers import about_video_sound_callback

    await about_video_sound_callback(update, context)

    q.answer.assert_awaited_once()
    context.bot.send_video.assert_awaited_once()
    assert "sound" in context.bot.send_video.call_args.kwargs["caption"].lower()
    footer = context.bot.send_message.await_args_list[-1]
    assert footer.kwargs.get("reply_parameters") is None
    assert footer.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == REVIEWS_OPEN_CB


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
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_photo = AsyncMock()

    log_free = mocker.patch("music_sales.bot_handlers.append_free_download_event")

    await send_free_track(update, context)

    context.bot.send_document.assert_awaited_once()
    log_free.assert_called_once()
    kwargs = context.bot.send_document.call_args.kwargs
    assert kwargs["chat_id"] == 777
    assert kwargs["document"] == "doc_file_id_123"


@pytest.mark.asyncio
async def test_send_free_track_skips_duplicate_covers(mocker):
    mocker.patch(
        "music_sales.bot_handlers.load_file_ids_dict",
        return_value={FREE_TRACK_TITLE: "doc_file_id_123"},
    )
    mocker.patch("music_sales.bot_handlers.Path.is_file", return_value=True)
    mocker.patch(
        "music_sales.bot_handlers.render_free_track_cover_for_telegram",
        return_value=b"png",
    )

    class _SentPhoto:
        def __init__(self, message_id: int) -> None:
            self.message_id = message_id

    photo_id = {"n": 500}

    async def _send_photo(**_kwargs):
        photo_id["n"] += 1
        return _SentPhoto(photo_id["n"])

    update = MagicMock()
    q = MagicMock()
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.chat_id = 777
    q.message.message_id = 40
    update.callback_query = q
    update.effective_chat = MagicMock()
    update.effective_chat.id = 777
    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_photo = AsyncMock(side_effect=_send_photo)

    await send_free_track(update, context)
    first_photo_count = context.bot.send_photo.await_count
    assert first_photo_count == 3
    assert len(context.chat_data.get("free_track_gallery_message_ids", [])) == 3

    await send_free_track(update, context)
    assert context.bot.send_photo.await_count == first_photo_count
    gift_texts = [
        (c.args[0] if c.args else c.kwargs.get("text", ""))
        for c in context.bot.send_message.await_args_list
    ]
    assert any("already shown above" in t for t in gift_texts)


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
    visitor.username = "michael"
    visitor.first_name = "Michael"
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
