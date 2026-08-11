"""Тесты отображения зачёркнутой + актуальной цены."""

from music_sales import pricing_display as pd


def test_compare_at_defaults(monkeypatch):
    monkeypatch.delenv("COMPARE_AT_PRICE_USD", raising=False)
    monkeypatch.delenv("COMPARE_AT_PRICE_SEK", raising=False)
    monkeypatch.delenv("DEFAULT_TRACK_PRICE_USD", raising=False)
    monkeypatch.delenv("CHECKOUT_SEK_UNIT_AMOUNT", raising=False)
    monkeypatch.setattr("music_sales.config.COMPARE_AT_PRICE_USD", "100")
    monkeypatch.setattr("music_sales.config.COMPARE_AT_PRICE_SEK", "1000")
    monkeypatch.setattr("music_sales.config.DEFAULT_TRACK_PRICE_USD", "15")
    monkeypatch.setattr("music_sales.config.CHECKOUT_SEK_UNIT_AMOUNT", "15000")

    assert pd.compare_at_price_usd() == 100
    assert pd.compare_at_price_sek() == 1000
    assert pd.current_price_usd() == 15
    assert pd.current_price_sek() == 150
    assert pd.usd_compare_display() == "$100"
    assert pd.usd_now_display() == "$15"
    assert pd.sek_compare_display() == "1000 SEK"
    assert pd.sek_now_display() == "150 SEK"
    assert "<s>$100</s>" in pd.usd_pair_html()
    assert "<b>$15</b>" in pd.usd_pair_html()
    assert "$15" in pd.usd_pair_plain()
    assert "\u0336" in pd.usd_pair_plain()


def test_track_usd_sek_premium_overrides(monkeypatch):
    monkeypatch.setenv("DEFAULT_TRACK_PRICE_USD", "15")
    monkeypatch.setenv("CHECKOUT_SEK_UNIT_AMOUNT", "15000")
    assert pd.track_usd_sek({"usd_price": 29, "sek_price": 290, "price_amount": 2900}) == (29, 290)
    assert pd.track_usd_sek({"usd_price": 49, "sek_price": 490, "price_amount": 4900}) == (49, 490)
    assert pd.track_usd_sek({"price_amount": 1500}) == (15, 150)


def test_usd_pair_plain_zero_does_not_fall_back_to_default(monkeypatch):
    """usd=0 должен дать $0, а не дефолт $15 (None → default)."""
    monkeypatch.setenv("DEFAULT_TRACK_PRICE_USD", "15")
    monkeypatch.setattr("music_sales.config.DEFAULT_TRACK_PRICE_USD", "15")
    assert pd.usd_now_display(0) == "$0"
    assert "$0" in pd.usd_pair_plain(0)
    assert "$15" not in pd.usd_pair_plain(0).split()[-1] or pd.usd_pair_plain(0).endswith("$0")
    assert pd.usd_pair_plain(0).endswith("$0")
    assert "<b>$0</b>" in pd.usd_pair_html(0)


def test_track_usd_sek_free_is_zero(monkeypatch):
    monkeypatch.setenv("DEFAULT_TRACK_PRICE_USD", "15")
    assert pd.track_usd_sek({"price": "FREE", "price_amount": 0}) == (0, 0)
    assert pd.track_usd_sek({"price_amount": 0}) == (0, 0)


def test_bot_detail_price_line_free_and_zero(monkeypatch):
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.setenv("DEFAULT_TRACK_PRICE_USD", "15")
    import bot as bot_mod

    monkeypatch.setattr(bot_mod, "_test_mode", lambda: False)
    assert bot_mod._detail_price_line({"price": "FREE", "price_amount": 0}) == "🎁 FREE"
    assert bot_mod._detail_price_line({"price_amount": 0}) == "🎁 FREE"
    line = bot_mod._detail_price_line({"usd_price": 29, "sek_price": 290, "price_amount": 2900})
    assert "$29" in line
    assert "$15" not in line.split("$29")[-1]  # актуальная цена — 29, не дефолт

