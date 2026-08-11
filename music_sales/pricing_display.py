"""
Отображение цен витрины: текущая + зачёркнутая «старая» (без слов old/current).

Пример: ~~$100~~ $15 · ~~1000 SEK~~ 150 SEK
Поддерживает разные цены по трекам (usd_price / sek_price в tracks.py).
"""

from __future__ import annotations

import os
from typing import Any

from music_sales import config


def _env_int(name: str, fallback: str, *, minimum: int = 1) -> int:
    raw = (os.environ.get(name) or getattr(config, name, None) or fallback).strip() or fallback
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return max(minimum, int(fallback))


def current_price_usd() -> int:
    """Актуальная цена по умолчанию в целых USD (live; не TEST_MODE)."""
    return _env_int("DEFAULT_TRACK_PRICE_USD", "15")


def current_price_sek() -> int:
    """Актуальная цена по умолчанию в целых SEK (из CHECKOUT_SEK_UNIT_AMOUNT в öre)."""
    ore = _env_int("CHECKOUT_SEK_UNIT_AMOUNT", "15000", minimum=100)
    return max(1, ore // 100)


def compare_at_price_usd() -> int:
    """Зачёркнутая «старая» цена USD (только для витрины)."""
    return _env_int("COMPARE_AT_PRICE_USD", "100")


def compare_at_price_sek() -> int:
    """Зачёркнутая «старая» цена SEK (только для витрины)."""
    return _env_int("COMPARE_AT_PRICE_SEK", "1000")


def strike_plain(text: str) -> str:
    """Зачёркивание через Unicode (кнопки Telegram без HTML)."""
    return "".join(ch + "\u0336" for ch in text)


def usd_now_display(usd: int | None = None) -> str:
    return f"${int(usd) if usd is not None else current_price_usd()}"


def sek_now_display(sek: int | None = None) -> str:
    return f"{int(sek) if sek is not None else current_price_sek()} SEK"


def usd_compare_display() -> str:
    return f"${compare_at_price_usd()}"


def sek_compare_display() -> str:
    return f"{compare_at_price_sek()} SEK"


def usd_pair_plain(usd: int | None = None) -> str:
    """Для текста без HTML: зачёркнутый $100 и актуальный $15 (или цена трека)."""
    return f"{strike_plain(usd_compare_display())} {usd_now_display(usd)}"


def sek_pair_plain(sek: int | None = None) -> str:
    return f"{strike_plain(sek_compare_display())} {sek_now_display(sek)}"


def usd_pair_html(usd: int | None = None) -> str:
    """Для Telegram parse_mode=HTML."""
    return f"<s>{usd_compare_display()}</s> <b>{usd_now_display(usd)}</b>"


def dual_pair_plain(usd: int | None = None, sek: int | None = None) -> str:
    """Обе валюты одной строкой (карточки /buy и т.п.)."""
    return f"{usd_pair_plain(usd)} · {sek_pair_plain(sek)}"


def track_usd_sek(track: dict[str, Any] | None) -> tuple[int, int]:
    """
    Целые USD и SEK для записи tracks.py / song-каталога.
    Приоритет: usd_price/sek_price → price_amount → дефолты env.
    """
    if not track:
        return current_price_usd(), current_price_sek()
    if str(track.get("price", "")).strip().upper() == "FREE":
        return 0, 0
    if track.get("price_amount") is not None:
        try:
            if int(track.get("price_amount")) == 0:
                return 0, 0
        except (TypeError, ValueError):
            pass

    usd: int | None = None
    if track.get("usd_price") is not None:
        try:
            usd = max(1, int(track["usd_price"]))
        except (TypeError, ValueError):
            usd = None
    if usd is None and track.get("price_usd") is not None:
        try:
            usd = max(1, int(track["price_usd"]))
        except (TypeError, ValueError):
            usd = None
    if usd is None and track.get("price_amount") is not None:
        try:
            usd = max(1, int(track["price_amount"]) // 100)
        except (TypeError, ValueError):
            usd = None
    if usd is None:
        usd = current_price_usd()

    sek: int | None = None
    if track.get("sek_price") is not None:
        try:
            sek = max(1, int(track["sek_price"]))
        except (TypeError, ValueError):
            sek = None
    if sek is None:
        sek = current_price_sek()
    return usd, sek
