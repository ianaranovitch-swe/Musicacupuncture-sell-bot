"""
Простой журнал продаж для /admin → «Статистика».
Записи добавляет webhook сервера после успешной оплаты.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from music_sales.catalog import project_root


def _sales_path() -> Path:
    return project_root() / "sales_log.json"


def append_sale_event(
    *,
    song_id: str,
    track_title: str,
    currency: str = "",
    source: str = "",
    session_id: str = "",
    telegram_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    path = _sales_path()
    entries: list[dict[str, Any]] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries = raw
        except (json.JSONDecodeError, OSError):
            entries = []
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "song_id": song_id,
        "track_title": track_title,
        "currency": currency or "",
        "source": source or "",
        "session_id": session_id or "",
    }
    if telegram_id is not None:
        row["telegram_id"] = telegram_id
    if extra:
        row.update(extra)
    entries.append(row)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_sales_entries() -> list[dict[str, Any]]:
    path = _sales_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, OSError):
        return []
