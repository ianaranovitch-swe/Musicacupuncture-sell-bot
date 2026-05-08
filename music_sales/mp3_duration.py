"""
Длительность MP3 для Mini App и бота: mutagen читает файл, короткая строка для UI (английский формат).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def mp3_duration_seconds(path: Path) -> int | None:
    """Длительность .mp3 в секундах (округление), или None если файла нет / не MP3 / ошибка."""
    if not path.is_file() or path.suffix.lower() != ".mp3":
        return None
    try:
        from mutagen.mp3 import MP3

        audio = MP3(str(path))
    except Exception:
        return None
    if audio.info is None or getattr(audio.info, "length", None) is None:
        return None
    try:
        return max(0, int(round(float(audio.info.length))))
    except (TypeError, ValueError):
        return None


def format_duration_short(seconds: int | None) -> str | None:
    """
    Короткий текст для UI: 50m 8s, 1h 2m, 45s.
    Тексты интерфейса — латиница/цифры (подходит для Telegram на английском).
    """
    if seconds is None or seconds < 0:
        return None
    sec = int(seconds)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        if m and s:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{h}h {m}m"
        if s:
            return f"{h}h {s}s"
        return f"{h}h"
    if m:
        return f"{m}m {s}s" if s else f"{m}m"
    return f"{s}s"


def miniapp_track_durations_for_pricing(root: Path | None = None) -> list[dict[str, Any]]:
    """
    Список для JSON Mini App: id как на фронте после sync (0 = бесплатный, остальные = реальные id в tracks).

    create-payment: track_id = id карточки; для бесплатного UI id 0 читаем файл бесплатного трека из каталога.
    """
    from music_sales.catalog import project_root
    from music_sales.frontend_catalog_sync import ordered_frontend_pairs
    from tracks import TRACKS, get_track

    base = root if root is not None else project_root()

    out: list[dict[str, Any]] = []
    for display_id, t in ordered_frontend_pairs(TRACKS):
        tid = int(t["id"])
        # Длительность всегда по реальному id и файлу audio в каталоге.
        t_lookup = get_track(tid)
        if not t_lookup:
            out.append({"id": display_id, "seconds": None, "label": None})
            continue
        rel = str(t_lookup.get("audio", "") or "").strip()
        ap = base / rel if rel else None
        sec = mp3_duration_seconds(ap) if ap else None
        label = format_duration_short(sec)
        out.append({"id": display_id, "seconds": sec, "label": label})
    return out
