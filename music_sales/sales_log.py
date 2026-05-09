"""
Журнал продаж и бесплатных выдач для /admin → «Статистика».

Поддержка Railway:
- при старте можно загрузить JSON из SALES_LOG_JSON;
- после каждой записи файл sales_log.json обновляется;
- текущий JSON также кладётся в os.environ["SALES_LOG_JSON"] (в пределах процесса).
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import URLError
from typing import Any

from music_sales.catalog import project_root


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


def _read_entries() -> list[dict[str, Any]]:
    """Основной источник — файл; если файла нет, берём env SALES_LOG_JSON."""
    path = _sales_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return raw
        except (json.JSONDecodeError, OSError):
            pass
    return _load_sales_from_env()


def _write_entries(entries: list[dict[str, Any]]) -> None:
    """Пишем в файл, обновляем env процесса и (опционально) Railway Variables."""
    payload = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
    _sales_path().write_text(payload, encoding="utf-8")
    os.environ["SALES_LOG_JSON"] = payload
    _sync_sales_log_to_railway(payload)


def _sync_sales_log_to_railway(payload: str) -> None:
    """
    Опциональная синхронизация SALES_LOG_JSON в Railway через GraphQL API.

    Включается только когда явно задано:
    - ENABLE_SALES_LOG_RAILWAY_SYNC=1
    - RAILWAY_API_TOKEN
    - RAILWAY_PROJECT_ID
    - RAILWAY_ENVIRONMENT_ID
    - RAILWAY_SERVICE_ID
    """
    if (os.environ.get("ENABLE_SALES_LOG_RAILWAY_SYNC") or "").strip() != "1":
        return
    token = (os.environ.get("RAILWAY_API_TOKEN") or "").strip()
    project_id = (os.environ.get("RAILWAY_PROJECT_ID") or "").strip()
    environment_id = (os.environ.get("RAILWAY_ENVIRONMENT_ID") or "").strip()
    service_id = (os.environ.get("RAILWAY_SERVICE_ID") or "").strip()
    if not token or not project_id or not environment_id or not service_id:
        return

    query = """
    mutation UpsertVars($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input) { id }
    }
    """
    body = {
        "query": query,
        "variables": {
            "input": {
                "projectId": project_id,
                "environmentId": environment_id,
                "serviceId": service_id,
                "variables": [
                    {"name": "SALES_LOG_JSON", "value": payload},
                ],
            }
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        "https://backboard.railway.app/graphql/v2",
        method="POST",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
            # Railway может вернуть 200 c errors — считаем нефатальным, но это полезно для диагностики.
            if isinstance(parsed, dict) and parsed.get("errors"):
                raise RuntimeError(str(parsed.get("errors")))
    except (URLError, OSError, RuntimeError, json.JSONDecodeError):
        # Нефатально: продажи уже записаны локально.
        return


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
    entries = _read_entries()
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


def append_free_download_event(*, telegram_user_id: int | None = None, track_title: str = "") -> None:
    """Лог бесплатной выдачи трека (для блока FREE DOWNLOADS в статистике)."""
    entries = _read_entries()
    now = datetime.now(timezone.utc)
    row: dict[str, Any] = {
        "event_type": "free_download",
        "ts": now.isoformat(),
        "track_title": track_title,
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


def read_sales_entries() -> list[dict[str, Any]]:
    return _read_entries()
