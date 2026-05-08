"""
Лог действий админов в admin_log.json (рядом с корнем проекта).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from music_sales.catalog import project_root


def _log_path() -> Path:
    return project_root() / "admin_log.json"


def append_admin_log(*, user_id: int, action: str, detail: dict[str, Any] | None = None) -> None:
    """Добавить одну запись с UTC-временем."""
    path = _log_path()
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
        "user_id": int(user_id),
        "action": str(action),
    }
    if detail:
        row["detail"] = detail
    entries.append(row)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
