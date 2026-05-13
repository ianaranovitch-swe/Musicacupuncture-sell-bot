from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from music_sales import config

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac"}
_FREE_BONUS_STEM = "Divine sound Super Feng Shui from God"


def project_root() -> Path:
    return Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))


def _audio_sales_dir_name() -> str:
    """Имя папки с треками: сначала `os.environ` (для тестов и .env), иначе `config.AUDIO_SALES_DIR`."""
    env = (os.environ.get("AUDIO_SALES_DIR") or "").strip()
    if env:
        return env
    name = (config.AUDIO_SALES_DIR or "songs").strip()
    return name or "songs"


def songs_dir() -> Path:
    return project_root() / _audio_sales_dir_name()


def songs_dir_under(root: Path) -> Path:
    """Папка с MP3 относительно заданного корня (например project_root_override на сервере)."""
    return root / _audio_sales_dir_name()


def _fixed_track_price_usd() -> int:
    """
    Фиксированная цена трека в целых долларах США (USD) для всех треков.

    Значение можно задать через переменные окружения, но продуктовый дефолт — $16.
    При TEST_MODE — берём TEST_PRICE_USD (по умолчанию 1).
    """
    if config.test_mode_active():
        raw = (os.environ.get("TEST_PRICE_USD") or config.TEST_PRICE_USD or "1").strip() or "1"
        try:
            return max(1, int(raw))
        except ValueError:
            return 1
    primary = (config.DEFAULT_TRACK_PRICE_USD or "").strip()
    legacy = (config.DEFAULT_TRACK_PRICE_SEK or "").strip()
    raw = primary or legacy or "16"
    try:
        return int(raw)
    except ValueError:
        return 16


def _load_catalog_json(folder: Path) -> Dict[str, Dict[str, Any]]:
    """
    Опциональный `songs/catalog.json` (или `<AUDIO_SALES_DIR>/catalog.json`):
      { "Track.mp3": { "name": "Красивое имя для кнопки" } }

    Важно: цены из JSON игнорируются — витрина использует фиксированную USD-цену из кода/окружения.
    """
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
    """Telegram ограничивает callback_data 64 байтами — делаем безопасный ASCII id."""
    s = re.sub(r"[^\w\-]", "_", stem, flags=re.ASCII)
    s = re.sub(r"_+", "_", s).strip("_")[:64]
    return s or "track"


def _track_dict_is_free_gift(t: dict[str, Any]) -> bool:
    """Совпадает с витриной: FREE по полю price или нулевой price_amount."""
    if str(t.get("price", "")).strip().upper() == "FREE":
        return True
    try:
        if int(t.get("price_amount") or -1) == 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def resolve_song_id_by_audio_stem(stem: str) -> str | None:
    """
    Находит song_id в каталоге discover_songs() по stem имени файла .mp3
    (совпадает с логикой имён из папки songs).

    Если на диске нет папки songs/ или файлов (часто Railway) — пробуем tracks.py:
    тот же stem даёт тот же базовый song_id, что и при сканировании диска.
    """
    stem = (stem or "").strip()
    if not stem:
        return None
    for song_id, meta in discover_songs().items():
        file_stem = Path(str(meta.get("file", ""))).stem
        if file_stem == stem:
            return song_id
    try:
        from tracks import TRACKS
    except ImportError:
        return None
    for t in TRACKS:
        if Path(str(t.get("audio", "") or "")).stem != stem:
            continue
        if _track_dict_is_free_gift(t):
            return None
        return _song_id_from_stem(stem)
    return None


def synthetic_song_row_for_song_id(song_id: str) -> dict[str, Any] | None:
    """
    Строка каталога как у discover_songs(), но только из tracks.py (без MP3 на диске).

    Нужна для website checkout / скачивания на Railway, где в репозитории нет бинарников songs/.
    """
    sid = (song_id or "").strip()
    if not sid:
        return None
    try:
        from tracks import TRACKS
    except ImportError:
        return None
    for t in TRACKS:
        stem = Path(str(t.get("audio", "") or "")).stem
        if not stem or _song_id_from_stem(stem) != sid:
            continue
        if _track_dict_is_free_gift(t):
            return None
        name = str(t.get("title") or stem)
        dir_name = _audio_sales_dir_name()
        fname = Path(str(t.get("audio", "") or f"{stem}.mp3")).name
        return {
            "name": name,
            "price_usd": _fixed_track_price_usd(),
            "file": f"{dir_name}/{fname}",
        }
    return None


def discover_songs() -> Dict[str, Dict[str, Any]]:
    """
    Сканирует папку `songs/` (или значение `AUDIO_SALES_DIR`) и собирает аудио-файлы (по одному треку на файл).

    Опционально `catalog.json` в этой папке может задать отображаемое имя, но не цену.
    """
    folder = songs_dir()
    if not folder.is_dir():
        return {}

    dir_name = _audio_sales_dir_name()
    overrides = _load_catalog_json(folder)
    default_price = _fixed_track_price_usd()
    out: Dict[str, Dict[str, Any]] = {}
    used_ids: set[str] = set()

    paths = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and p.name != "catalog.json"
    ]
    for path in sorted(paths, key=lambda p: p.name.lower()):
        # Бесплатный бонус-трек не продаём и не добавляем в платный каталог (он выдаётся отдельной кнопкой 🎁).
        if path.stem == _FREE_BONUS_STEM:
            continue
        ov = overrides.get(path.name, {})
        name = ov.get("name") if isinstance(ov.get("name"), str) else None
        if not name:
            name = path.stem.replace("_", " ").strip() or path.stem
        # Требование продукта: все треки продаются по фиксированной USD-цене.
        # `catalog.json` в папке треков может менять отображаемое имя, но не цену.
        price_usd = default_price

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
            "price_usd": price_usd,
            "file": f"{dir_name}/{path.name}",
        }

    return out


def free_bonus_audio_path(base: Path | None = None) -> Path:
    """
    Путь к бесплатному бонус-треку на диске (тот же файл, что у бота по file_id).

    Файл намеренно не входит в discover_songs() — отдельная выдача через /free-track.
    """
    root = base if base is not None else project_root()
    return songs_dir_under(root) / f"{_FREE_BONUS_STEM}.mp3"


def song_path(song_id: str) -> Path:
    songs = discover_songs()
    return project_root() / songs[song_id]["file"]


def unit_amount_for_song(song: Dict[str, Any]) -> int:
    """Сумма для Stripe в минимальных единицах валюты (для USD: центы, т.е. USD × 100)."""
    return int(song["price_usd"] * 100)


def stripe_unit_amount_cents(song_id: str) -> int:
    return unit_amount_for_song(discover_songs()[song_id])


# Обратная совместимость (старое имя функции)
stripe_unit_amount_ore = stripe_unit_amount_cents
