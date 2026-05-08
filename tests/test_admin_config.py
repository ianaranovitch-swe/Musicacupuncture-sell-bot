"""ADMIN_IDS в config (читается из os.environ при каждом вызове)."""


def test_admin_telegram_ids_empty(monkeypatch):
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    from music_sales import config

    assert config.admin_telegram_ids() == set()


def test_admin_telegram_ids_parsed(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", " 111 , 222 , bad ,333 ")
    from music_sales import config

    assert config.admin_telegram_ids() == {111, 222, 333}
