"""
Загрузка и сохранение testimonials.py (корень репозитория).
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path
from typing import Any

from music_sales.catalog import project_root


def _testimonials_path() -> Path:
    return project_root() / "testimonials.py"


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
    """Все отзывы из файла (включая скрытые)."""
    try:
        from testimonials import testimonials as data
    except ImportError:
        return []
    if not isinstance(data, list):
        return []
    return [dict(x) for x in data if isinstance(x, dict)]


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
