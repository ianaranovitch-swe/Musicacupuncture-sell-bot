"""
Журнал продаж и бесплатных выдач для /admin → «Статистика».

Поддержка Railway (эфемерный диск):
- при старте bootstrap_sales_log() объединяет sales_log.json и SALES_LOG_JSON;
- после каждой записи файл и os.environ["SALES_LOG_JSON"] обновляются;
- опционально ENABLE_SALES_LOG_RAILWAY_SYNC=1 пишет JSON в Variables Railway.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from music_sales.catalog import project_root

logger = logging.getLogger(__name__)

# Бесплатный подарок в боте (Super Feng Shui) — отдельная метрика в статистике.
FREE_GIFT_TRACK_TITLE = "Divine sound Super Feng Shui from God"


def _sales_path() -> Path:
    return project_root() / "sales_log.json"


def _load_sales_from_env() -> list[dict[str, Any]]:
    """Читаем резервный журнал из SALES_LOG_JSON (если задан и валиден)."""
    raw = (os.environ.get("SALES_LOG_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _read_entries_from_file() -> list[dict[str, Any]]:
    path = _sales_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _entry_dedupe_key(e: dict[str, Any]) -> str:
    """Ключ для слияния записей без дублей (файл + env после рестарта)."""
    et = str(e.get("event_type") or "")
    ts = str(e.get("ts") or "")
    if et == "free_download":
        return "|".join(
            (
                et,
                ts,
                str(e.get("telegram_user_id") or ""),
                str(e.get("track_title") or ""),
            )
        )
    tid = str(e.get("transaction_id") or e.get("session_id") or "")
    return "|".join(
        (
            et,
            ts,
            tid,
            str(e.get("track_title") or e.get("song_id") or ""),
        )
    )


def _merge_entries(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entries in lists:
        for e in entries:
            if not isinstance(e, dict):
                continue
            merged[_entry_dedupe_key(e)] = e
    out = list(merged.values())
    out.sort(key=lambda row: str(row.get("ts") or ""))
    return out


def _load_sales_from_railway_api() -> list[dict[str, Any]]:
    """Актуальный журнал из Shared SALES_LOG_JSON (только worker, не web)."""
    try:
        from music_sales.railway_vars_sync import (
            fetch_railway_variable_value,
            railway_sales_log_fetch_allowed,
        )

        if not railway_sales_log_fetch_allowed():
            return []
        raw = (fetch_railway_variable_value("SALES_LOG_JSON") or "").strip()
    except Exception:
        logger.debug("SALES_LOG_JSON fetch from Railway skipped or failed", exc_info=True)
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def read_sales_entries_local() -> list[dict[str, Any]]:
    """Только файл + env (для web snapshot, без Railway API)."""
    return _merge_entries(_read_entries_from_file(), _load_sales_from_env())


def _read_entries(*, fetch_remote: bool = False) -> list[dict[str, Any]]:
    sources = [_read_entries_from_file(), _load_sales_from_env()]
    if fetch_remote:
        sources.append(_load_sales_from_railway_api())
    return _merge_entries(*sources)


def _read_entries_for_append() -> list[dict[str, Any]]:
    from music_sales.railway_vars_sync import railway_sales_log_fetch_allowed

    return _read_entries(fetch_remote=railway_sales_log_fetch_allowed())


def _write_entries(entries: list[dict[str, Any]], *, push_railway: bool = True) -> None:
    """Пишем в файл, обновляем env процесса и (опционально) Railway Variables."""
    payload = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
    path = _sales_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    os.environ["SALES_LOG_JSON"] = payload
    if push_railway:
        _sync_sales_log_to_railway(payload)


def bootstrap_sales_log() -> int:
    """
    При старте бота/сервера: слить файл и SALES_LOG_JSON, сохранить обратно.
    Возвращает число записей в журнале.
    """
    merged = _read_entries(fetch_remote=False)
    if merged:
        _write_entries(merged, push_railway=False)
        logger.info("sales_log bootstrap: %d entries persisted (file + SALES_LOG_JSON)", len(merged))
    else:
        logger.info("sales_log bootstrap: empty log (counting starts on first sale/free gift)")
    return len(merged)


def _sync_sales_log_to_railway(payload: str) -> None:
    from music_sales.railway_vars_sync import sync_sales_log_json_to_railway

    sync_sales_log_json_to_railway(payload)


def _normalize_track_title(name: str) -> str:
    s = str(name or "").lower()
    s = s.replace("-", " ").replace("—", " ")
    return re.sub(r"\s+", " ", s).strip()


def _is_free_gift_download(e: dict[str, Any]) -> bool:
    if str(e.get("event_type") or "") != "free_download":
        return False
    title = _normalize_track_title(str(e.get("track_title") or ""))
    if not title:
        return True
    return title == _normalize_track_title(FREE_GIFT_TRACK_TITLE)


def count_free_gift_downloads(entries: list[dict[str, Any]]) -> int:
    return sum(1 for e in entries if _is_free_gift_download(e))


def free_gift_counting_started_label(entries: list[dict[str, Any]]) -> str:
    """Дата первой записи бесплатной выдачи (UTC) или подсказка, что счёт ещё не начался."""
    times: list[datetime] = []
    for e in entries:
        if not _is_free_gift_download(e):
            continue
        raw = str(e.get("ts") or "").strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            times.append(dt)
        except ValueError:
            continue
    if not times:
        return "not started yet (first download will begin the count)"
    first = min(times).astimezone(timezone.utc)
    return first.strftime("%Y-%m-%d %H:%M UTC")


def append_sale_event(
    *,
    song_id: str,
    track_title: str,
    track_id: int | None = None,
    amount: float | None = None,
    currency: str = "",
    source: str = "",
    session_id: str = "",
    transaction_id: str = "",
    telegram_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    entries = _read_entries_for_append()
    now = datetime.now(timezone.utc)
    row: dict[str, Any] = {
        "event_type": "sale",
        "ts": now.isoformat(),
        "song_id": song_id,
        "track_id": int(track_id) if track_id is not None else None,
        "track_title": track_title,
        "transaction_id": transaction_id or session_id or "",
        "amount": float(amount) if amount is not None else 0.0,
        "currency": currency or "",
        "source": source or "",
        "session_id": session_id or "",
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "week": int(now.strftime("%V")),
        "month": now.month,
        "year": now.year,
    }
    if telegram_id is not None:
        row["telegram_user_id"] = telegram_id
    if extra:
        row.update(extra)
    entries.append(row)
    _write_entries(entries)
    logger.info(
        "sale logged: source=%s track=%s amount=%s %s",
        row.get("source"),
        row.get("track_title"),
        row.get("amount"),
        row.get("currency"),
    )


def append_free_download_event(
    *,
    telegram_user_id: int | None = None,
    track_title: str = "",
    source: str = "bot",
) -> None:
    """Лог бесплатной выдачи трека (бот или сайт → /admin статистика FREE DOWNLOADS)."""
    entries = _read_entries_for_append()
    now = datetime.now(timezone.utc)
    row: dict[str, Any] = {
        "event_type": "free_download",
        "ts": now.isoformat(),
        "track_title": track_title or FREE_GIFT_TRACK_TITLE,
        "source": (source or "bot").strip() or "bot",
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "week": int(now.strftime("%V")),
        "month": now.month,
        "year": now.year,
    }
    if telegram_user_id is not None:
        row["telegram_user_id"] = int(telegram_user_id)
    entries.append(row)
    _write_entries(entries)
    logger.info(
        "free_download logged: user_id=%s source=%s total_free=%d",
        telegram_user_id,
        row["source"],
        count_free_gift_downloads(entries),
    )


def read_sales_entries() -> list[dict[str, Any]]:
    from music_sales.railway_vars_sync import railway_sales_log_fetch_allowed

    return _read_entries(fetch_remote=railway_sales_log_fetch_allowed())
