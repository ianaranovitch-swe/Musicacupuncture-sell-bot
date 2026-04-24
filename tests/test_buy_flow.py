from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from music_sales.buy_callbacks import buy_pay_method, buy_track_select
from music_sales.buy_command import buy
from music_sales.buy_constants import PAY_CB_LINK, PAY_CB_TELEGRAM, UD_PENDING_SONG_ID, pay_method_callback
from music_sales.buy_payments import pre_checkout, successful_payment


_SAMPLE_SONGS = {
    "s1": {"name": "Relaxing Sound", "price_usd": 16, "file": "songs/s1.mp3"},
    "s2": {"name": "Deep Sleep Track", "price_usd": 16, "file": "songs/wav_only.wav"},
}


@pytest.mark.asyncio
async def test_buy_lists_only_mp3(mocker):
    mocker.patch("music_sales.buy_command.discover_songs", return_value=_SAMPLE_SONGS)

    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 1

    await buy(update, MagicMock())

    update.message.reply_text.assert_awaited_once()
    markup = update.message.reply_text.call_args[1]["reply_markup"]
    assert len(markup.inline_keyboard) == 1


@pytest.mark.asyncio
async def test_buy_track_select_sets_pending_and_shows_pay_methods(mocker):
    mocker.patch("music_sales.buy_callbacks.discover_songs", return_value=_SAMPLE_SONGS)

    update = MagicMock()
    query = MagicMock()
    query.data = "b:t:000"
    query.from_user = MagicMock()
    query.from_user.id = 999
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}

    await buy_track_select(update, context)

    assert context.user_data[UD_PENDING_SONG_ID] == "s1"
    query.message.reply_text.assert_awaited_once()
    pay_markup = query.message.reply_text.call_args[1]["reply_markup"]
    texts = [btn.text for row in pay_markup.inline_keyboard for btn in row]
    assert any("Telegram" in t for t in texts)
    assert any("external" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_buy_pay_method_external_checkout(mocker):
    mocker.patch("music_sales.buy_callbacks.discover_songs", return_value=_SAMPLE_SONGS)
    mock_post = mocker.patch("music_sales.buy_callbacks.requests.post")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"url": "https://checkout.example/pay"}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    update = MagicMock()
    query = MagicMock()
    query.data = pay_method_callback(PAY_CB_LINK)
    query.from_user = MagicMock()
    query.from_user.id = 999
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {UD_PENDING_SONG_ID: "s1"}
    context.bot.send_invoice = AsyncMock()

    await buy_pay_method(update, context)

    mock_post.assert_called_once()
    context.bot.send_invoice.assert_not_called()
    query.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_buy_pay_method_telegram_invoice(mocker):
    mocker.patch("music_sales.buy_callbacks.discover_songs", return_value=_SAMPLE_SONGS)
    mocker.patch("music_sales.buy_callbacks.config.PAYMENTS_PROVIDER_TOKEN", "prov_test")
    mocker.patch("music_sales.buy_callbacks.config.PAYMENTS_CURRENCY", "USD")

    update = MagicMock()
    query = MagicMock()
    query.data = pay_method_callback(PAY_CB_TELEGRAM)
    query.from_user = MagicMock()
    query.from_user.id = 999
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 123
    update.callback_query = query

    context = MagicMock()
    context.user_data = {UD_PENDING_SONG_ID: "s1"}
    context.bot.send_invoice = AsyncMock()

    await buy_pay_method(update, context)

    context.bot.send_invoice.assert_awaited_once()
    kwargs = context.bot.send_invoice.call_args[1]
    assert kwargs["currency"] == "USD"
    assert kwargs["payload"] == "ms|s1|999"


@pytest.mark.asyncio
async def test_pre_checkout_rejects_bad_payload():
    update = MagicMock()
    q = MagicMock()
    q.invoice_payload = "bad"
    q.from_user = MagicMock()
    q.from_user.id = 1
    q.currency = "USD"
    q.total_amount = 1600
    q.answer = AsyncMock()
    update.pre_checkout_query = q

    await pre_checkout(update, MagicMock())

    q.answer.assert_awaited_once_with(ok=False, error_message=ANY)


@pytest.mark.asyncio
async def test_successful_payment_sends_audio(mocker):
    mocker.patch("music_sales.buy_payments.discover_songs", return_value=_SAMPLE_SONGS)

    fake_path = MagicMock()
    fake_path.is_file.return_value = True
    fake_path.name = "s1.mp3"

    fh = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = fh
    cm.__exit__.return_value = False
    fake_path.open.return_value = cm

    mocker.patch("music_sales.buy_payments.song_path", return_value=fake_path)

    update = MagicMock()
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = 999
    sp = MagicMock()
    sp.invoice_payload = "ms|s1|999"
    msg.successful_payment = sp
    msg.reply_text = AsyncMock()
    msg.reply_audio = AsyncMock()
    update.message = msg

    await successful_payment(update, MagicMock())

    msg.reply_audio.assert_awaited_once()
