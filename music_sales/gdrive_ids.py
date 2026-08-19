"""
Google Drive file_id для выдачи MP3 на сайте (после Stripe), без MP3 на диске Railway.

Приоритет ключей (как FILE_IDS_JSON для бота):
  1) поле google_drive_file_id уже в строке каталога
  2) GDRIVE_IDS_JSON из Railway (stem или title → id)
  3) встроенные ID из tracks.py (_BUILTIN_GOOGLE_DRIVE_IDS)

Публичная ссылка drive.google.com/uc?export=download НЕ используется: файлы приватные,
доступ только через Service Account (см. google_drive_delivery.py — стрим alt=media).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _builtin_gdrive_ids_by_stem() -> dict[str, str]:
    """ID из tracks.py: ключ = stem MP3 (имя файла без .mp3)."""
    try:
        from tracks import TRACKS, reload_track_catalog

        reload_track_catalog()
    except ImportError:
        return {}

    out: dict[str, str] = {}
    for t in TRACKS:
        stem = Path(str(t.get("audio", "") or "")).stem
        gid = str(t.get("google_drive_file_id") or "").strip()
        if stem and gid:
            out[stem] = gid
        title = str(t.get("title") or "").strip()
        if title and gid and title not in out:
            out[title] = gid
    return out


def load_gdrive_ids_dict() -> dict[str, str]:
    """
    Словарь stem/title → Google Drive file_id.

    Сначала встроенные ID из tracks.py, затем поверх — GDRIVE_IDS_JSON из env (Railway).
    """
    merged = dict(_builtin_gdrive_ids_by_stem())
    raw = (os.environ.get("GDRIVE_IDS_JSON") or "").strip()
    if not raw:
        return merged
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("GDRIVE_IDS_JSON is not valid JSON: %s", e)
        return merged
    if not isinstance(data, dict):
        logger.error("GDRIVE_IDS_JSON must be a JSON object")
        return merged
    for k, v in data.items():
        ks, vs = str(k).strip(), str(v).strip()
        if ks and vs:
            merged[ks] = vs
    return merged


def tracks_missing_google_drive_ids() -> list[dict[str, Any]]:
    """
    Треки из tracks.py без google_drive_file_id.

    Сайт после Stripe не может скачать MP3 >20 MB через Telegram getFile —
    без Drive-ID покупатель видит ошибку «20 MB».
    """
    try:
        from tracks import TRACKS, reload_track_catalog

        reload_track_catalog()
    except ImportError:
        return []

    missing: list[dict[str, Any]] = []
    for t in TRACKS:
        gid = str(t.get("google_drive_file_id") or "").strip()
        if gid:
            continue
        stem = Path(str(t.get("audio") or "")).stem
        missing.append(
            {
                "id": t.get("id"),
                "title": str(t.get("title") or stem),
                "stem": stem,
            }
        )
    return missing


def song_requires_drive_for_website(song: dict[str, Any]) -> bool:
    """
    Mozart / Super-Mozart ~40–50 MB: Telegram getFile на сайте всегда падает.
    Тогда нужен google_drive_file_id (как у Divine sound).
    """
    if str(song.get("google_drive_file_id") or "").strip():
        return True
    rel = str(song.get("file") or song.get("audio") or "").strip()
    stem = Path(rel).stem if rel else ""
    name = str(song.get("name") or "").strip()
    blob = f"{stem} {name}"
    return "Mozart+" in blob or "Mozart +" in blob or stem.startswith("Super-Mozart")


def google_drive_file_id_for_song(
    song: dict[str, Any],
    gdrive_ids: dict[str, str] | None = None,
) -> str | None:
    """
    Найти Drive file_id для строки каталога (website /download-file).

    Порядок: google_drive_file_id в song → stem файла → name → словарь GDRIVE_IDS_JSON + tracks.
    """
    direct = str(song.get("google_drive_file_id") or "").strip()
    if direct:
        return direct

    ids = gdrive_ids if gdrive_ids is not None else load_gdrive_ids_dict()
    if not ids:
        return None

    rel = str(song.get("file") or "").strip()
    if rel:
        stem = Path(rel).stem
        if stem and stem in ids:
            return ids[stem]

    name = str(song.get("name") or "").strip()
    if name and name in ids:
        return ids[name]

    return None
