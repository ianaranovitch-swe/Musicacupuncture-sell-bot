"""
Слияние журнала продаж с web-сервиса в worker (без Railway GraphQL на web).

Web пишет события локально (файл + SALES_LOG_JSON env). Worker раз в N секунд
забирает снимок по HTTPS и объединяет в общий журнал (+ push в Shared Variable).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import request as urlrequest
from urllib.error import URLError

from music_sales import config

logger = logging.getLogger(__name__)


def _pull_secret() -> str:
    return (os.environ.get("SALES_LOG_PULL_SECRET") or "").strip()


def _web_public_base_url() -> str:
    for key in ("WEB_PUBLIC_URL", "DOMAIN", "BACKEND_URL"):
        raw = (os.environ.get(key) or "").strip().rstrip("/")
        if raw:
            if not raw.startswith("http"):
                raw = f"https://{raw}"
            return raw
    return (config.DOMAIN or config.BACKEND_URL or "").strip().rstrip("/")


def fetch_web_sales_log_snapshot() -> list[dict[str, Any]]:
    """GET /internal/sales-log-snapshot на web (только с секретом)."""
    secret = _pull_secret()
    base = _web_public_base_url()
    if not secret or not base:
        return []
    url = f"{base}/internal/sales-log-snapshot"
    req = urlrequest.Request(
        url,
        method="GET",
        headers={"X-Sales-Log-Secret": secret},
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
    except (URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
        logger.debug("sales log pull from web failed: %s", exc)
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("entries")
    if not isinstance(entries, list):
        return []
    return [dict(x) for x in entries if isinstance(x, dict)]


def pull_sales_log_from_web() -> int:
    """
    Worker: объединить локальный журнал + снимок с web, сохранить (+ Railway sync на worker).
    Возвращает число записей, пришедших с web в этом цикле (после dedupe — приблизительно).
    """
    web_entries = fetch_web_sales_log_snapshot()
    if not web_entries:
        return 0
    from music_sales.railway_vars_sync import railway_sales_log_fetch_allowed
    from music_sales.sales_log import (
        _merge_entries,
        _read_entries,
        _write_entries,
        read_sales_entries,
    )

    before = len(read_sales_entries())
    merged = _merge_entries(_read_entries(fetch_remote=railway_sales_log_fetch_allowed()), web_entries)
    _write_entries(merged, push_railway=True)
    after = len(merged)
    added = max(0, after - before)
    if added:
        logger.info("sales log: merged %d new entries from website (total %d)", added, after)
    return added
