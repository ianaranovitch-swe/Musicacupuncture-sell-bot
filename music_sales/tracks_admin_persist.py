"""
Чтение/запись JSON-слоёв каталога (tracks_extra, overrides, deleted).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from music_sales.catalog import project_root


def _root() -> Path:
    return project_root()


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extras_path() -> Path:
    return _root() / "tracks_extra.json"


def overrides_path() -> Path:
    return _root() / "track_overrides.json"


def deleted_path() -> Path:
    return _root() / "tracks_deleted.json"


def read_extras() -> list[dict[str, Any]]:
    raw = _read(extras_path(), [])
    return raw if isinstance(raw, list) else []


def write_extras(items: list[dict[str, Any]]) -> None:
    _write(extras_path(), items)


def read_overrides() -> dict[str, Any]:
    raw = _read(overrides_path(), {})
    return raw if isinstance(raw, dict) else {}


def write_overrides(data: dict[str, Any]) -> None:
    _write(overrides_path(), data)


def read_deleted_ids() -> list[int]:
    raw = _read(deleted_path(), [])
    out: list[int] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def write_deleted_ids(ids: list[int]) -> None:
    _write(deleted_path(), sorted(set(ids)))


def sanitize_filename_stem(name: str, max_len: int = 80) -> str:
    """Безопасное имя файла (без путей)."""
    s = (name or "").strip()
    s = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip() or "track"
    return s[:max_len]


def append_extra_track(track: dict[str, Any]) -> None:
    items = read_extras()
    items.append(track)
    write_extras(items)


def remove_extra_track_by_id(track_id: int) -> bool:
    items = read_extras()
    new_items = [t for t in items if int(t.get("id", -1)) != int(track_id)]
    if len(new_items) == len(items):
        return False
    write_extras(new_items)
    return True


def set_override(track_id: int, patch: dict[str, Any]) -> None:
    ov = read_overrides()
    key = str(int(track_id))
    cur = ov.get(key)
    if not isinstance(cur, dict):
        cur = {}
    cur.update(patch)
    ov[key] = cur
    write_overrides(ov)


def clear_override_key(track_id: int) -> None:
    """Удалить весь override для id (редко нужно)."""
    ov = read_overrides()
    ov.pop(str(int(track_id)), None)
    write_overrides(ov)


def add_deleted_id(track_id: int) -> None:
    cur = set(read_deleted_ids())
    cur.add(int(track_id))
    write_deleted_ids(sorted(cur))
