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


def test_compare_at_custom_env(monkeypatch):
    monkeypatch.setenv("COMPARE_AT_PRICE_USD", "200")
    monkeypatch.setenv("COMPARE_AT_PRICE_SEK", "2000")
    monkeypatch.setenv("DEFAULT_TRACK_PRICE_USD", "15")
    monkeypatch.setenv("CHECKOUT_SEK_UNIT_AMOUNT", "15000")
    assert pd.compare_at_price_usd() == 200
    assert pd.compare_at_price_sek() == 2000
