"""
Синхронизация каталога TRACKS с miniapp.html и website.html (автоблок между маркерами).

Вызывается после изменений в админке, чтобы GitHub Pages / статика совпадали с ботом и Railway.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from music_sales.catalog import project_root

logger = logging.getLogger(__name__)

# Маркеры внутри <script> — только JS-комментарии (HTML <!-- ломает разбор скрипта).
MINIAPP_BEGIN = "    /* MA_AUTO_TRACKS_BEGIN */"
MINIAPP_END = "    /* MA_AUTO_TRACKS_END */"
WEBSITE_BEGIN = "  /* MA_AUTO_SITE_TRACKS_BEGIN */"
WEBSITE_END = "  /* MA_AUTO_SITE_TRACKS_END */"

# Только для классического бесплатного трека — три обложки в галерее Mini App.
_GALLERY_SUPER_FENG_SHUI = [
    "covers/Divine-sound-Super-Feng-Shui-from-God.png",
    "covers/Divine sound Super Feng Shui from God CD cover front.png",
    "covers/Divine sound Super Feng Shui from God CD cover back.png",
]


def is_free_track(t: dict[str, Any]) -> bool:
    """Бесплатный трек: по полю price или нулевой price_amount."""
    if str(t.get("price", "")).strip().upper() == "FREE":
        return True
    try:
        if int(t.get("price_amount") or -1) == 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def peel_emoji_short(short_title: str) -> tuple[str, str]:
    """
    Делим short_title на эмодзи и короткое имя (как в старом miniapp.html: «🎵 Estrogen» → 🎵 + Estrogen).
    Если первое «слово» выглядит как латиница — считаем, что эмодзи нет, ставим 🎵.
    """
    s = (short_title or "").strip() or "Track"
    parts = s.split(None, 1)
    if len(parts) == 1:
        return "🎵", parts[0]
    first, rest = parts[0], parts[1]
    if any("a" <= c.lower() <= "z" for c in first):
        return "🎵", s
    return (first if first else "🎵"), rest


def _gallery_covers_miniapp(t: dict[str, Any], is_free: bool) -> list[str] | None:
    """Для известного подарка — три картинки; иначе None (фронт возьмёт [cover])."""
    if not is_free:
        return None
    stem = Path(str(t.get("audio") or "")).stem
    if stem == "Divine sound Super Feng Shui from God":
        return list(_GALLERY_SUPER_FENG_SHUI)
    return None


def ordered_frontend_pairs(tracks: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    """
    Порядок как на сайте: сначала бесплатный с id 0 в UI, затем платные по возрастанию реального id.
    Реальные id в каталоге бота не трогаем — в JSON для фронта кладём display_id.
    """
    free = [t for t in tracks if is_free_track(t)]
    paid = sorted((t for t in tracks if not is_free_track(t)), key=lambda x: int(x["id"]))
    out: list[tuple[int, dict[str, Any]]] = []
    if free:
        out.append((0, free[0]))
    for t in paid:
        out.append((int(t["id"]), t))
    return out


def miniapp_js_block(tracks: list[dict[str, Any]]) -> str:
    """Текст: const tracks = [ ... ]; (с отступами как в файле)."""
    rows: list[str] = []
    for display_id, t in ordered_frontend_pairs(tracks):
        emoji, short_name = peel_emoji_short(str(t.get("short_title") or ""))
        is_free = display_id == 0
        full_title = str(t.get("title") or "")
        desc = str(t.get("description") or "")
        cover = str(t.get("cover") or "").replace("\\", "/").strip()
        obj: dict[str, Any] = {
            "id": display_id,
            "emoji": emoji,
            "shortName": short_name,
            "fullTitle": full_title,
            "description": desc,
            "cover": cover,
        }
        if is_free:
            obj["isFree"] = True
        gal = _gallery_covers_miniapp(t, is_free)
        if gal:
            obj["galleryCovers"] = gal
        line = "      " + json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))
        rows.append(line)
    inner = ",\n".join(rows)
    return f"    const tracks = [\n{inner}\n    ];"


def website_js_block(tracks: list[dict[str, Any]]) -> str:
    """Текст: const TRACKS = [ ... ];"""
    rows: list[str] = []
    for display_id, t in ordered_frontend_pairs(tracks):
        emoji, short_name = peel_emoji_short(str(t.get("short_title") or ""))
        is_free = display_id == 0
        full_title = str(t.get("title") or "")
        desc = str(t.get("description") or "")
        cover = str(t.get("cover") or "").replace("\\", "/").strip()
        obj: dict[str, Any] = {
            "id": display_id,
            "emoji": emoji,
            "shortName": short_name,
            "fullTitle": full_title,
            "description": desc,
            "cover": cover,
        }
        if is_free:
            obj["isFree"] = True
            obj["buyUrl"] = None
            obj["buyUrlUsd"] = None
            obj["buyUrlSek"] = None
        else:
            usd = str(t.get("buy_url") or "").strip()
            sek = str(t.get("buy_url_sek") or "").strip()
            obj["buyUrlUsd"] = usd or None
            obj["buyUrlSek"] = sek or None
        line = "    " + json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))
        rows.append(line)
    inner = ",\n".join(rows)
    return f"  const TRACKS = [\n{inner}\n  ];"


def _replace_marked_region(html: str, begin: str, end: str, new_block: str) -> str | None:
    """
    Между begin и end вставляем new_block (уже с переводами строк).
    Возвращает None, если маркеры не найдены.
    """
    i0 = html.find(begin)
    i1 = html.find(end)
    if i0 < 0 or i1 < 0 or i1 <= i0:
        return None
    i1_end = i1 + len(end)
    return html[:i0] + begin + "\n" + new_block + "\n" + end + html[i1_end:]


def _fallback_replace_miniapp(html: str, new_block: str) -> str | None:
    """Если маркеров нет — один раз оборачиваем const tracks = [ ... ]; в маркеры."""
    m = re.search(r"    const tracks = \[\n[\s\S]*?\n    \];\n", html)
    if not m:
        return None
    return (
        html[: m.start()]
        + MINIAPP_BEGIN
        + "\n"
        + new_block
        + "\n"
        + MINIAPP_END
        + "\n"
        + html[m.end() :]
    )


def _fallback_replace_website(html: str, new_block: str) -> str | None:
    m = re.search(r"  const TRACKS = \[\n[\s\S]*?\n  \];\n", html)
    if not m:
        return None
    return (
        html[: m.start()]
        + WEBSITE_BEGIN
        + "\n"
        + new_block
        + "\n"
        + WEBSITE_END
        + "\n"
        + html[m.end() :]
    )


@dataclass
class FrontendSyncResult:
    written: list[str]
    errors: list[str]


def sync_frontend_html_catalog(
    root: Path | None = None,
    tracks: list[dict[str, Any]] | None = None,
) -> FrontendSyncResult:
    """
    Перечитать tracks.TRACKS и обновить автоблоки в HTML (корень и _site при наличии).

    tracks — опционально (для тестов); иначе берётся живой TRACKS из tracks.py.

    Не падает при ошибке одного файла — копит errors.
    """
    if tracks is None:
        from tracks import TRACKS as tracks_src
    else:
        tracks_src = tracks

    base = root if root is not None else project_root()
    written: list[str] = []
    errors: list[str] = []

    mini_block = miniapp_js_block(tracks_src)
    web_block = website_js_block(tracks_src)

    targets = [
        (base / "miniapp.html", MINIAPP_BEGIN, MINIAPP_END, mini_block, _fallback_replace_miniapp),
        (base / "website.html", WEBSITE_BEGIN, WEBSITE_END, web_block, _fallback_replace_website),
        (base / "_site" / "miniapp.html", MINIAPP_BEGIN, MINIAPP_END, mini_block, _fallback_replace_miniapp),
        (base / "_site" / "website.html", WEBSITE_BEGIN, WEBSITE_END, web_block, _fallback_replace_website),
    ]

    for path, begin, end, block, fallback in targets:
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            updated = _replace_marked_region(raw, begin, end, block)
            if updated is None:
                updated = fallback(raw, block)
            if updated is None:
                errors.append(f"{path}: markers or pattern not found")
                continue
            if updated != raw:
                path.write_text(updated, encoding="utf-8", newline="\n")
            written.append(str(path))
        except OSError as e:
            errors.append(f"{path}: {e}")
            logger.warning("frontend sync failed: %s", e)

    return FrontendSyncResult(written=written, errors=errors)
