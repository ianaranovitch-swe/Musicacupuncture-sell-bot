"""
Отображение цен витрины: текущая + зачёркнутая «старая» (без слов old/current).

Пример: ~~$100~~ $15 · ~~1000 SEK~~ 150 SEK
"""

from __future__ import annotations

import os

from music_sales import config


def _env_int(name: str, fallback: str, *, minimum: int = 1) -> int:
    raw = (os.environ.get(name) or getattr(config, name, None) or fallback).strip() or fallback
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return max(minimum, int(fallback))


def current_price_usd() -> int:
    """Актуальная цена в целых USD (live; не TEST_MODE)."""
    return _env_int("DEFAULT_TRACK_PRICE_USD", "15")


def current_price_sek() -> int:
    """Актуальная цена в целых SEK (из CHECKOUT_SEK_UNIT_AMOUNT в öre)."""
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


def usd_now_display() -> str:
    return f"${current_price_usd()}"


def sek_now_display() -> str:
    return f"{current_price_sek()} SEK"


def usd_compare_display() -> str:
    return f"${compare_at_price_usd()}"


def sek_compare_display() -> str:
    return f"{compare_at_price_sek()} SEK"


def usd_pair_plain() -> str:
    """Для текста без HTML: зачёркнутый $100 и актуальный $15."""
    return f"{strike_plain(usd_compare_display())} {usd_now_display()}"


def sek_pair_plain() -> str:
    return f"{strike_plain(sek_compare_display())} {sek_now_display()}"


def usd_pair_html() -> str:
    """Для Telegram parse_mode=HTML."""
    return f"<s>{usd_compare_display()}</s> <b>{usd_now_display()}</b>"


def dual_pair_plain() -> str:
    """Обе валюты одной строкой (карточки /buy и т.п.)."""
    return f"{usd_pair_plain()} · {sek_pair_plain()}"
