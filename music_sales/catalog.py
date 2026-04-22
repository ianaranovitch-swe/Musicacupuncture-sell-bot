from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from music_sales import config

SONGS_DIR_NAME = "SONGS"

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac"}


def project_root() -> Path:
    return Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))


def songs_dir() -> Path:
    return project_root() / SONGS_DIR_NAME


def _default_price_sek() -> int:
    try:
        return int(config.DEFAULT_TRACK_PRICE_SEK or "50")
    except ValueError:
        return 50


def _load_catalog_json(folder: Path) -> Dict[str, Dict[str, Any]]:
    """Optional SONGS/catalog.json: { \"Track.mp3\": { \"name\": \"...\", \"price_sek\": 70 } }"""
    meta = folder / "catalog.json"
    if not meta.is_file():
        return {}
    try:
        raw = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for fname, val in raw.items():
        if isinstance(fname, str) and isinstance(val, dict):
            out[fname] = val
    return out


def _song_id_from_stem(stem: str) -> str:
    """Telegram callback_data is max 64 bytes; use safe ASCII id."""
    s = re.sub(r"[^\w\-]", "_", stem, flags=re.ASCII)
    s = re.sub(r"_+", "_", s).strip("_")[:64]
    return s or "track"


def discover_songs() -> Dict[str, Dict[str, Any]]:
    """
    Scan the SONGS folder for audio files. One button per file.
    Optional SONGS/catalog.json can set display name and price_sek per filename.
    """
    folder = songs_dir()
    if not folder.is_dir():
        return {}

    overrides = _load_catalog_json(folder)
    default_price = _default_price_sek()
    out: Dict[str, Dict[str, Any]] = {}
    used_ids: set[str] = set()

    paths = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and p.name != "catalog.json"
    ]
    for path in sorted(paths, key=lambda p: p.name.lower()):
        ov = overrides.get(path.name, {})
        name = ov.get("name") if isinstance(ov.get("name"), str) else None
        if not name:
            name = path.stem.replace("_", " ").strip() or path.stem
        price = ov.get("price_sek", default_price)
        try:
            price_sek = int(price)
        except (TypeError, ValueError):
            price_sek = default_price
        if price_sek < 1:
            price_sek = default_price

        base_id = _song_id_from_stem(path.stem)
        song_id = base_id
        n = 2
        while song_id in used_ids:
            suffix = f"_{n}"
            song_id = (base_id[: 64 - len(suffix)] + suffix) if len(base_id) + len(suffix) > 64 else base_id + suffix
            n += 1
        used_ids.add(song_id)

        out[song_id] = {
            "name": name,
            "price_sek": price_sek,
            "file": f"{SONGS_DIR_NAME}/{path.name}",
        }

    return out


def song_path(song_id: str) -> Path:
    songs = discover_songs()
    return project_root() / songs[song_id]["file"]


def unit_amount_for_song(song: Dict[str, Any]) -> int:
    """Stripe amount in minor currency units (SEK × 100)."""
    return int(song["price_sek"] * 100)


def stripe_unit_amount_ore(song_id: str) -> int:
    return unit_amount_for_song(discover_songs()[song_id])
