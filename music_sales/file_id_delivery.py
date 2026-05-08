"""
Доставка купленных треков через Telegram file_id (без чтения MP3 с диска на Railway).

Ключи в JSON совпадают с upload_songs.py: stem имени файла из tracks.py (например
«Divine sound Vitamins from God»). Дополнительно пробуем поле name из каталога.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _file_ids_json_path() -> Path:
    """Локальный file_ids.json в корне проекта (как upload_songs.py)."""
    return Path(__file__).resolve().parent.parent / "file_ids.json"


def load_file_ids_from_disk() -> dict[str, str]:
    """Читаем file_ids.json с диска; пустой/битый файл → {}."""
    p = _file_ids_json_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("file_ids.json read failed: %s", e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in data.items() if str(k).strip() and str(v).strip()}

# Текст под файлом в Telegram (английский UI по правилам проекта)
PURCHASE_DELIVERY_CAPTION = (
    "🎵 Thank you for your purchase!\nListen daily for best results. 🙏"
)


def load_file_ids_dict() -> dict[str, str]:
    """
    Словарь stem/name → file_id: сначала file_ids.json в корне репо, затем поверх — FILE_IDS_JSON из env
    (переменная окружения перекрывает совпадающие ключи — удобно для Railway).
    """
    merged = dict(load_file_ids_from_disk())
    raw = (os.environ.get("FILE_IDS_JSON") or "").strip()
    if not raw:
        return merged
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("FILE_IDS_JSON is not valid JSON: %s", e)
        return merged
    if not isinstance(data, dict):
        return merged
    for k, v in data.items():
        if k is not None and v is not None:
            ks, vs = str(k).strip(), str(v).strip()
            if ks and vs:
                merged[ks] = vs
    return merged


def file_id_for_song(song: dict[str, Any], file_ids: dict[str, str] | None = None) -> str | None:
    """
    Находим file_id для трека из каталога discover_songs().

    Порядок ключей (как в upload_songs.py — там key = Path(audio).stem):
    1) stem относительного пути file (songs/foo.mp3 → foo)
    2) отображаемое имя name
    """
    ids = file_ids if file_ids is not None else load_file_ids_dict()
    if not ids:
        return None

    file_rel = str(song.get("file", "") or "").strip()
    if file_rel:
        stem = Path(file_rel).stem
        if stem and stem in ids:
            return ids[stem]

    name = str(song.get("name", "") or "").strip()
    if name and name in ids:
        return ids[name]

    return None
