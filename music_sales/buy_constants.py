"""Константы и утилиты для сценария покупки через /buy.

В Telegram поле `callback_data` ограничено 64 байтами, поэтому мы не кладём туда длинные `song_id`.
Вместо этого используем короткий числовой индекс, который соответствует отсортированным строкам каталога.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Префиксы callback_data (короткие, чтобы не упираться в лимит Telegram 64 байта)
CB_BUY_TRACK_PREFIX = "b:t:"  # b:t:<idx>
CB_BUY_PAY_PREFIX = "b:p:"  # b:p:tg|lk

PAY_CB_TELEGRAM = "tg"
PAY_CB_LINK = "lk"

# Ключи user_data
UD_PENDING_SONG_ID = "buy_pending_song_id"


@dataclass(frozen=True)
class BuySongRow:
    """Одна строка каталога для /buy (порядок совпадает с inline-клавиатурой)."""

    song_id: str
    name: str
    price_usd: int


def sorted_buy_rows(songs: Dict[str, dict]) -> List[BuySongRow]:
    rows: List[BuySongRow] = []
    for song_id, meta in sorted(songs.items(), key=lambda kv: kv[1]["name"].lower()):
        rows.append(
            BuySongRow(
                song_id=song_id,
                name=str(meta["name"]),
                price_usd=int(meta["price_usd"]),
            )
        )
    return rows


def index_to_callback(idx: int) -> str:
    # 3 цифры => до 1000 треков; при необходимости можно расширить формат.
    return f"{CB_BUY_TRACK_PREFIX}{idx:03d}"


def parse_track_index(callback_data: str) -> int | None:
    if not callback_data.startswith(CB_BUY_TRACK_PREFIX):
        return None
    tail = callback_data[len(CB_BUY_TRACK_PREFIX) :]
    if not tail.isdigit():
        return None
    return int(tail)


def pay_method_callback(method: str) -> str:
    return f"{CB_BUY_PAY_PREFIX}{method}"


def parse_pay_method(callback_data: str) -> str | None:
    if not callback_data.startswith(CB_BUY_PAY_PREFIX):
        return None
    return callback_data[len(CB_BUY_PAY_PREFIX) :]


def build_invoice_payload(*, song_id: str, user_id: int) -> str:
    """Payload для Telegram Payments (максимум 128 байт)."""
    # Формат: ms|<song_id>|<user_id>
    return f"ms|{song_id}|{user_id}"


def parse_invoice_payload(payload: str) -> Tuple[str, int] | None:
    if not payload or payload.count("|") != 2:
        return None
    prefix, song_id, uid_s = payload.split("|", 2)
    if prefix != "ms" or not song_id or not uid_s.isdigit():
        return None
    return song_id, int(uid_s)
