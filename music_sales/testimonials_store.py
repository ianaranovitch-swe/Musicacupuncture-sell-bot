"""
Загрузка и сохранение testimonials.py (корень репозитория).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from music_sales.catalog import project_root
from music_sales.railway_vars_sync import sync_testimonials_json_to_railway

logger = logging.getLogger(__name__)


def _testimonials_path() -> Path:
    return project_root() / "testimonials.py"


def _testimonials_json_path() -> Path:
    return project_root() / "testimonials.json"


def _load_testimonials_from_env() -> list[dict[str, Any]]:
    raw = (os.environ.get("TESTIMONIALS_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [dict(x) for x in data if isinstance(x, dict)]


def _read_testimonials_json_file() -> list[dict[str, Any]]:
    path = _testimonials_json_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [dict(x) for x in data if isinstance(x, dict)]


def _load_testimonials_from_py() -> list[dict[str, Any]]:
    try:
        from testimonials import testimonials as data
    except ImportError:
        return []
    if not isinstance(data, list):
        return []
    return [dict(x) for x in data if isinstance(x, dict)]


def _merge_testimonials_by_id(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Поздние источники перекрывают ранние (env/json важнее py после bootstrap)."""
    by_id: dict[int, dict[str, Any]] = {}
    for items in lists:
        for item in items:
            try:
                tid = int(item.get("id", -1))
            except (TypeError, ValueError):
                continue
            if tid < 0:
                continue
            by_id[tid] = dict(item)
    return sorted(by_id.values(), key=lambda x: int(x.get("id") or 0))


def _persist_testimonials_json_and_env(items: list[dict[str, Any]]) -> None:
    payload = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    path = _testimonials_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    os.environ["TESTIMONIALS_JSON"] = payload
    sync_testimonials_json_to_railway(payload)


def bootstrap_testimonials() -> int:
    """
    При старте бота/сервера: слить testimonials.py, testimonials.json и TESTIMONIALS_JSON.
    """
    merged = _merge_testimonials_by_id(
        _load_testimonials_from_py(),
        _read_testimonials_json_file(),
        _load_testimonials_from_env(),
    )
    if merged:
        _persist_testimonials_json_and_env(merged)
        logger.info("testimonials bootstrap: %d reviews (file + TESTIMONIALS_JSON)", len(merged))
    else:
        logger.info("testimonials bootstrap: no reviews found")
    return len(merged)


def _normalize_track_key(name: str) -> str:
    """Сравнение названий треков без регистра, дефисов и лишних пробелов."""
    s = str(name or "").lower()
    s = s.replace("-", " ").replace("—", " ")
    return re.sub(r"\s+", " ", s).strip()


def reload_testimonials_module() -> None:
    """Перечитать testimonials.py после записи с диска."""
    import testimonials as mod

    importlib.reload(mod)


def load_all_testimonials() -> list[dict[str, Any]]:
    """Все отзывы (py + json + TESTIMONIALS_JSON), включая скрытые."""
    return _merge_testimonials_by_id(
        _load_testimonials_from_py(),
        _read_testimonials_json_file(),
        _load_testimonials_from_env(),
    )


def load_visible_testimonials() -> list[dict[str, Any]]:
    return [t for t in load_all_testimonials() if t.get("visible", True) is not False]


def save_testimonials(items: list[dict[str, Any]]) -> None:
    """Перезаписать testimonials.py (формат как в репозитории)."""
    path = _testimonials_path()
    lines = [
        '"""',
        "Отзывы клиентов (Customer Reviews).",
        "",
        "Редактируется вручную или через /admin → Manage Reviews.",
        "Поле visible=False скрывает отзыв на сайте и в боте.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "testimonials: list[dict] = [",
    ]
    for item in items:
        lines.append("    {")
        for key in ("id", "name", "city", "track", "rating", "visible", "text"):
            if key not in item:
                continue
            val = item[key]
            if key == "text":
                lines.append(f'        "text": {repr(str(val))},')
            elif isinstance(val, bool):
                lines.append(f'        "{key}": {val!r},')
            elif isinstance(val, int):
                lines.append(f'        "{key}": {int(val)},')
            else:
                lines.append(f'        "{key}": {repr(str(val))},')
        lines.append("    },")
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    _persist_testimonials_json_and_env(items)
    reload_testimonials_module()


def next_testimonial_id(items: list[dict[str, Any]]) -> int:
    ids = [int(x.get("id", 0)) for x in items if str(x.get("id", "")).isdigit()]
    return (max(ids) if ids else 0) + 1


def find_testimonial_by_id(items: list[dict[str, Any]], tid: int) -> dict[str, Any] | None:
    for t in items:
        if int(t.get("id", -1)) == int(tid):
            return t
    return None


def find_testimonials_for_track(track_title: str, *, visible_only: bool = True) -> list[dict[str, Any]]:
    """Отзывы по полному названию трека (как в tracks.py / fullTitle на сайте)."""
    key = _normalize_track_key(track_title)
    if not key:
        return []
    pool = load_visible_testimonials() if visible_only else load_all_testimonials()
    return [t for t in pool if _normalize_track_key(str(t.get("track") or "")) == key]


def rating_stars(rating: int) -> str:
    r = max(0, min(5, int(rating or 0)))
    return "⭐" * r if r else "⭐"


def first_sentence(text: str, max_len: int = 120) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    for sep in (". ", "! ", "? "):
        if sep in raw:
            part = raw.split(sep, 1)[0] + sep.strip()
            if len(part) <= max_len:
                return part
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1].rstrip() + "…"


def format_telegram_review(item: dict[str, Any], *, index: int, total: int) -> str:
    """Текст одного отзыва для Telegram."""
    stars = rating_stars(int(item.get("rating") or 5))
    name = str(item.get("name") or "").strip()
    city = str(item.get("city") or "").strip()
    track = str(item.get("track") or "").strip()
    text = str(item.get("text") or "").strip()
    header = f"{stars} {name}, {city}\n\n🎵 Track: {track}\n\n'{text}'"
    footer = f"\n\nReview {index} of {total}"
    return header + footer
