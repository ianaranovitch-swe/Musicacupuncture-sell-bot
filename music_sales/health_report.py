"""
Сводка «здоровья» деплоя: 17 MP3, обложки, ключевые env и проверки API.
Используется командой /health (только владелец) и GET /health на Flask.
"""

from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests
from telegram import Update
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.catalog import discover_songs, free_bonus_audio_path, project_root, songs_dir
from tracks import TRACKS

logger = logging.getLogger(__name__)

def _paid_tracks_count() -> int:
    """Треки с ценой (не FREE) — должны совпасть с discover_songs() без бонусного файла."""
    return sum(1 for t in TRACKS if str(t.get("price", "")).strip().upper() != "FREE")


def _stripe_balance_ok() -> Tuple[bool, str]:
    """Проверка Stripe по секретному ключу (без вывода ключа)."""
    sk = (config.STRIPE_SECRET_KEY or "").strip()
    if not sk:
        return False, "STRIPE_SECRET_KEY not set"
    try:
        import stripe

        stripe.api_key = sk
        stripe.Balance.retrieve()
        return True, "Stripe Balance.retrieve OK"
    except Exception as e:
        return False, f"Stripe error: {e!s}"[:200]


def _backend_options_ok() -> Tuple[bool, str]:
    """OPTIONS /create-payment — CORS/preflight и доступность Web."""
    base = (config.BACKEND_URL or "").strip().rstrip("/")
    if not base:
        return False, "BACKEND_URL not set"
    low = base.lower()
    if not low.startswith("https://") and "localhost" not in low and "127.0.0.1" not in low:
        return False, "BACKEND_URL should use https:// in production (http allowed only for localhost)"
    url = f"{base}/create-payment"
    try:
        r = requests.options(url, timeout=10)
        if r.status_code in (200, 204):
            return True, f"OPTIONS /create-payment -> HTTP {r.status_code}"
        return False, f"OPTIONS /create-payment -> HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, f"request failed: {e!s}"[:200]


def _miniapp_env_ok() -> Tuple[bool, str]:
    url = config.resolved_miniapp_url()
    if url.startswith("https://"):
        return True, "MINIAPP_URL / DOMAIN yields HTTPS Mini App URL"
    if not url:
        return False, "Mini App URL not configured (MINIAPP_URL / https DOMAIN)"
    return False, "Mini App URL must be https:// for Telegram"


def _cors_configured() -> Tuple[bool, str]:
    raw = (config.MINIAPP_CORS_ORIGINS or "").strip()
    if not raw:
        return False, "MINIAPP_CORS_ORIGINS empty (Mini App checkout may fail CORS)"
    return True, f"CORS origins configured ({len(raw.split(','))} entries)"


def _file_ids_json_ok() -> Tuple[bool, str]:
    """После оплаты треки шлются по Telegram file_id из FILE_IDS_JSON (см. upload_songs.py)."""
    raw = (os.environ.get("FILE_IDS_JSON") or "").strip()
    if not raw:
        return False, "FILE_IDS_JSON not set (post-checkout delivery will fail)"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"FILE_IDS_JSON invalid JSON: {e!s}"[:200]
    if not isinstance(data, dict) or len(data) < 1:
        return False, "FILE_IDS_JSON must be a non-empty JSON object"
    return True, f"FILE_IDS_JSON OK ({len(data)} keys)"


def _free_track_bonus_mp3_relative(root: Path) -> str:
    """Относительный путь бонусного MP3 (для /health без абсолютных путей)."""
    p = free_bonus_audio_path(root)
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p.name)


def _free_track_website_ok() -> Tuple[bool, str]:
    """
    website.html: fetch GET BACKEND_URL/free-track, затем HEAD (или GET) по url из JSON.
    Не входит в ready — только диагностика (самопинг может флапать при неверном BACKEND_URL).
    """
    base = (config.BACKEND_URL or "").strip().rstrip("/")
    if not base:
        return False, "BACKEND_URL not set (cannot probe /free-track)"
    low = base.lower()
    if not low.startswith("https://") and "localhost" not in low and "127.0.0.1" not in low:
        return False, "BACKEND_URL must use https:// in production to probe /free-track"
    api = f"{base}/free-track"
    try:
        r = requests.get(api, timeout=12)
    except requests.RequestException as e:
        return False, f"GET /free-track failed: {e!s}"[:200]
    if r.status_code != 200:
        return False, f"GET /free-track -> HTTP {r.status_code}"
    try:
        data = r.json()
    except Exception as e:
        return False, f"/free-track not JSON: {e!s}"[:120]
    file_url = (data.get("url") or "").strip()
    if not file_url:
        return False, "/free-track JSON missing url"
    try:
        h = requests.head(file_url, timeout=12, allow_redirects=True)
        if h.status_code == 405:
            g = requests.get(file_url, timeout=12, stream=True)
            try:
                sc = g.status_code
            finally:
                g.close()
        else:
            sc = h.status_code
    except requests.RequestException as e:
        return False, f"MP3 URL request failed: {e!s}"[:200]
    if sc != 200:
        return False, f"free MP3 URL -> HTTP {sc}"
    return True, "GET /free-track + MP3 URL OK"


def build_health_report() -> Dict[str, Any]:
    """Собрать данные для /health (JSON). Без секретов в ответе."""
    root = project_root()
    missing_audio: List[str] = []
    missing_cover: List[str] = []
    for t in TRACKS:
        ap = root / str(t.get("audio", ""))
        cp = root / str(t.get("cover", ""))
        if not ap.is_file():
            missing_audio.append(str(t.get("audio", "")))
        if not cp.is_file():
            missing_cover.append(str(t.get("cover", "")))

    songs = discover_songs()
    mp3_in_catalog = sum(1 for _, v in songs.items() if str(v.get("file", "")).lower().endswith(".mp3"))
    present_cover_count = len(TRACKS) - len(missing_cover)
    paid_expected = _paid_tracks_count()
    n_tracks = len(TRACKS)
    folder = songs_dir()
    songs_folder_exists = folder.is_dir()
    expected_mp3_names = {Path(str(t.get("audio", ""))).name for t in TRACKS}
    extra_mp3: List[str] = []
    if songs_folder_exists:
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() == ".mp3" and p.name not in expected_mp3_names:
                extra_mp3.append(p.name)

    stripe_ok, stripe_msg = _stripe_balance_ok()
    backend_ok, backend_msg = _backend_options_ok()
    mini_ok, mini_msg = _miniapp_env_ok()
    cors_ok, cors_msg = _cors_configured()
    file_ids_ok, file_ids_msg = _file_ids_json_ok()
    bonus_path = free_bonus_audio_path(root)
    free_mp3_on_disk = bonus_path.is_file()
    free_mp3_rel = _free_track_bonus_mp3_relative(root)
    free_site_ok, free_site_msg = _free_track_website_ok()

    webhook_secret_set = bool((config.STRIPE_WEBHOOK_SECRET or "").strip())
    mini_secret_set = bool((config.MINIAPP_CHECKOUT_SECRET or "").strip())
    pay_token_set = bool((config.PAYMENTS_PROVIDER_TOKEN or "").strip())
    file_ids_set = bool((os.environ.get("FILE_IDS_JSON") or "").strip())

    return {
        "test_mode": config.test_mode_active(),
        "expected_tracks": n_tracks,
        "expected_paid_tracks": paid_expected,
        "tracks_py_entries": len(TRACKS),
        "songs_folder_exists": songs_folder_exists,
        "songs_folder": str(songs_dir()),
        "discovered_mp3_count": mp3_in_catalog,
        "missing_audio_from_tracks_py": missing_audio,
        "missing_covers_from_tracks_py": missing_cover,
        "audio_files_ok": len(missing_audio) == 0,
        "cover_files_ok": len(missing_cover) == 0,
        "mp3_count_matches_expected": mp3_in_catalog == paid_expected,
        "cover_count_matches_expected": present_cover_count == n_tracks,
        "present_cover_count": present_cover_count,
        "extra_mp3_files_not_in_tracks_py": extra_mp3,
        "free_track": {
            "bonus_mp3_relative": free_mp3_rel,
            "mp3_on_disk": free_mp3_on_disk,
        },
        "env": {
            "BOT_TOKEN_set": bool((config.BOT_TOKEN or "").strip()),
            "STRIPE_SECRET_KEY_set": bool((config.STRIPE_SECRET_KEY or "").strip()),
            "STRIPE_WEBHOOK_SECRET_set": webhook_secret_set,
            "MINIAPP_CHECKOUT_SECRET_set": mini_secret_set,
            "PAYMENTS_PROVIDER_TOKEN_set": pay_token_set,
            "FILE_IDS_JSON_set": file_ids_set,
            "BACKEND_URL_host": urlparse((config.BACKEND_URL or "http://localhost").strip() or "http://localhost").netloc
            or "(empty)",
            "DOMAIN_host": urlparse((config.DOMAIN or "http://localhost").strip() or "http://localhost").netloc
            or "(empty)",
        },
        "checks": {
            "stripe": {"ok": stripe_ok, "detail": stripe_msg},
            "backend_options": {"ok": backend_ok, "detail": backend_msg},
            "miniapp_url": {"ok": mini_ok, "detail": mini_msg},
            "miniapp_cors": {"ok": cors_ok, "detail": cors_msg},
            "file_ids_json": {"ok": file_ids_ok, "detail": file_ids_msg},
            "free_track_website": {"ok": free_site_ok, "detail": free_site_msg},
        },
        "ready": bool(
            len(missing_audio) == 0
            and len(missing_cover) == 0
            and len(extra_mp3) == 0
            and mp3_in_catalog == paid_expected
            and present_cover_count == n_tracks
            and stripe_ok
            and backend_ok
            and mini_ok
            and cors_ok
            and file_ids_ok
            and songs_folder_exists
        ),
    }


def format_health_html(report: Dict[str, Any], telegram_bot_line: str | None = None) -> str:
    """Короткий HTML для Telegram (английский UI)."""
    lines: List[str] = [
        "<b>Health report</b>",
        f"Ready: <b>{'YES' if report.get('ready') else 'NO'}</b>",
        "",
        "<b>Files (tracks.py)</b>",
        f"Expected MP3: {report.get('expected_tracks')}",
        f"Missing audio: {len(report.get('missing_audio_from_tracks_py') or [])}",
        f"Missing covers: {len(report.get('missing_covers_from_tracks_py') or [])}",
        f"Present covers: {report.get('present_cover_count')}",
        f"discover_songs() MP3 count: {report.get('discovered_mp3_count')}",
        f"Songs folder exists: {report.get('songs_folder_exists')}",
        "",
        "<b>Free track (website download)</b>",
        f"Bonus MP3 on disk: <b>{'YES' if (report.get('free_track') or {}).get('mp3_on_disk') else 'NO'}</b> "
        f"({html.escape(str((report.get('free_track') or {}).get('bonus_mp3_relative') or ''))})",
        "",
        "<b>Checks</b>",
    ]
    checks = report.get("checks") or {}
    for name, block in checks.items():
        ok = block.get("ok") if isinstance(block, dict) else False
        det = html.escape(str(block.get("detail", "")) if isinstance(block, dict) else "")
        lines.append(f"• {html.escape(name)}: {'OK' if ok else 'FAIL'} — {det}")
    if telegram_bot_line:
        lines.append("")
        lines.append(f"<b>Telegram bot</b>: {html.escape(telegram_bot_line)}")
    miss_a = report.get("missing_audio_from_tracks_py") or []
    miss_c = report.get("missing_covers_from_tracks_py") or []
    if miss_a:
        lines.append("")
        lines.append("<b>Missing audio paths</b>")
        for p in miss_a[:8]:
            lines.append(html.escape(str(p)))
        if len(miss_a) > 8:
            lines.append(f"… +{len(miss_a) - 8} more")
    if miss_c:
        lines.append("")
        lines.append("<b>Missing cover paths</b>")
        for p in miss_c[:8]:
            lines.append(html.escape(str(p)))
        if len(miss_c) > 8:
            lines.append(f"… +{len(miss_c) - 8} more")
    extra = report.get("extra_mp3_files_not_in_tracks_py") or []
    if extra:
        lines.append("")
        lines.append("<b>Extra MP3 in songs folder (not in tracks.py)</b>")
        for name in extra[:12]:
            lines.append(html.escape(str(name)))
        if len(extra) > 12:
            lines.append(f"… +{len(extra) - 12} more")
    lines.append("")
    lines.append("<b>Tips</b>: fix missing files, env on Railway Web/Worker, redeploy. LOG_FILE=- for Railway logs.")
    return "\n".join(lines)


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /health: владелец бота и разработчик (тексты ответа на английском)."""

    user = update.effective_user
    allowed = config.health_command_allowed_user_ids()
    if user is None or user.id not in allowed:
        if update.message:
            await update.message.reply_text(
                "This command is only for the bot owner or the developer."
            )
        return

    if not update.message:
        return

    report = build_health_report()
    tg_line = ""
    try:
        me = await context.bot.get_me()
        tg_line = f"OK @{me.username}" if me.username else f"OK (id {me.id})"
    except Exception as e:
        tg_line = f"FAIL: {e!s}"[:120]

    text = format_health_html(report, telegram_bot_line=tg_line)
    # Telegram limit 4096; разбиваем грубо по частям
    max_len = 3900
    if len(text) <= max_len:
        await update.message.reply_text(text, parse_mode="HTML")
        return
    chunk = 0
    while text:
        part = text[:max_len]
        text = text[max_len:]
        chunk += 1
        await update.message.reply_text(f"(part {chunk})\n{part}", parse_mode="HTML")
