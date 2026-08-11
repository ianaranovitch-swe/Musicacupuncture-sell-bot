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
from music_sales.pricing_display import track_usd_sek

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
    if t.get("price_amount") is not None:
        try:
            if int(t.get("price_amount")) == 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def is_premium_catalog_track(t: dict[str, Any]) -> bool:
    """
    Новая premium-серия (Mozart / Super Mozart), ids 19–32.
    По title «Mozart» или по диапазону id — чтобы блок не разъезжался.
    """
    title = str(t.get("title") or "")
    if "Mozart" in title:
        return True
    try:
        tid = int(t["id"])
    except (KeyError, TypeError, ValueError):
        return False
    return 19 <= tid <= 32


def sort_tracks_catalog_order(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Витрина: сначала все premium (14 Mozart), потом classic (free + старые платные).
    Внутри premium: featured+new выше, дальше по id.
    Внутри classic: free первым, затем featured+new, остальные по id.
    """
    premium = [t for t in tracks if is_premium_catalog_track(t)]
    classic = [t for t in tracks if not is_premium_catalog_track(t)]

    def _feat_id_key(x: dict[str, Any]) -> tuple[int, int]:
        feat = bool(x.get("is_featured")) and bool(x.get("is_new"))
        return (0 if feat else 1, int(x["id"]))

    premium_sorted = sorted(premium, key=_feat_id_key)
    free = [t for t in classic if is_free_track(t)]
    paid_classic = sorted((t for t in classic if not is_free_track(t)), key=_feat_id_key)
    return premium_sorted + free + paid_classic


def track_display_emoji_short(t: dict[str, Any]) -> tuple[str, str]:
    """
    Эмодзи и короткое имя для Mini App / website: приоритет у ui_emoji + ui_short_name из tracks.py
    (чтобы кнопка в боте могла быть длинной, а карточка — компактной).
    """
    ui_s = t.get("ui_short_name")
    if ui_s and str(ui_s).strip():
        raw_e = t.get("ui_emoji")
        emoji = (str(raw_e).strip() if raw_e is not None else "") or "🎵"
        return emoji, str(ui_s).strip()
    return peel_emoji_short(str(t.get("short_title") or ""))


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
    Порядок витрины: premium Mozart → classic (free с display id 0 + старые).
    Реальные id в боте не трогаем — в JSON для фронта у free кладём display_id=0.
    """
    out: list[tuple[int, dict[str, Any]]] = []
    for t in sort_tracks_catalog_order(tracks):
        if is_free_track(t):
            out.append((0, t))
        else:
            out.append((int(t["id"]), t))
    return out


def miniapp_js_block(tracks: list[dict[str, Any]]) -> str:
    """Текст: const tracks = [ ... ]; (с отступами как в файле)."""
    rows: list[str] = []
    for display_id, t in ordered_frontend_pairs(tracks):
        emoji, short_name = track_display_emoji_short(t)
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
        if bool(t.get("is_featured")):
            obj["isFeatured"] = True
        if bool(t.get("is_new")):
            obj["isNew"] = True
        if is_premium_catalog_track(t):
            obj["isPremium"] = True
        if is_free:
            obj["isFree"] = True
        else:
            usd_n, sek_n = track_usd_sek(t)
            obj["priceUsd"] = usd_n
            obj["priceSek"] = sek_n
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
        emoji, short_name = track_display_emoji_short(t)
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
        if bool(t.get("is_featured")):
            obj["isFeatured"] = True
        if bool(t.get("is_new")):
            obj["isNew"] = True
        if is_premium_catalog_track(t):
            obj["isPremium"] = True
        if is_free:
            obj["isFree"] = True
            obj["buyUrl"] = None
            obj["buyUrlUsd"] = None
            obj["buyUrlSek"] = None
        else:
            usd_n, sek_n = track_usd_sek(t)
            obj["priceUsd"] = usd_n
            obj["priceSek"] = sek_n
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
