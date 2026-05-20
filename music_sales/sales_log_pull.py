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
    if not secret:
        logger.warning(
            "sales log pull: SALES_LOG_PULL_SECRET not set on worker — "
            "website free downloads will not appear in /admin stats"
        )
        return []
    if not base:
        logger.warning(
            "sales log pull: set WEB_PUBLIC_URL=https://musicacupuncture.digital on worker"
        )
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
        logger.warning("sales log pull from web failed (%s): %s", url, exc)
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
    from music_sales.sales_log import (
        count_free_gift_downloads,
        merge_and_persist_sales_log,
        read_sales_entries,
    )

    before_free = count_free_gift_downloads(read_sales_entries())
    total = merge_and_persist_sales_log(web_entries)
    after_free = count_free_gift_downloads(read_sales_entries())
    added_free = max(0, after_free - before_free)
    if added_free:
        logger.info(
            "sales log: merged %d new free downloads from website (total entries %d, free %d)",
            added_free,
            total,
            after_free,
        )
    return added_free
