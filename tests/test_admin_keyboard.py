"""Кнопка 🔐 Admin внизу чата и доступ is_admin."""


def test_is_admin_includes_owner_and_admin_ids(mocker):
    mocker.patch("music_sales.admin_panel.config.admin_telegram_ids", return_value={111})
    mocker.patch("music_sales.admin_panel.config.owner_telegram_id_int", return_value=222)
    mocker.patch("music_sales.admin_panel.config.developer_telegram_id_int", return_value=333)
    from music_sales.admin_panel import is_admin

    assert is_admin(111) is True
    assert is_admin(222) is True
    assert is_admin(333) is True
    assert is_admin(999) is False


def test_admin_reply_keyboard_button_text():
    from music_sales.admin_panel import ADMIN_MENU_BUTTON_TEXT, admin_reply_keyboard

    kb = admin_reply_keyboard()
    assert kb.keyboard[0][0].text == ADMIN_MENU_BUTTON_TEXT


def test_admin_conversation_has_button_entry_point():
    from music_sales.admin_panel import build_admin_conversation_handler

    handler = build_admin_conversation_handler()
    assert len(handler.entry_points) >= 2
