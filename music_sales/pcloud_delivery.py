"""
Серверная выдача больших MP3 через pCloud (getfilelink + стрим на Railway).

Ссылку из getfilelink не отдаём клиенту — только стрим с backend после проверки оплаты.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _normalize_api_host(raw: str) -> str:
    h = (raw or "").strip().lower()
    if h.startswith("https://"):
        h = h[8:]
    if h.startswith("http://"):
        h = h[7:]
    h = h.split("/")[0].strip()
    return h or "api.pcloud.com"


def resolve_pcloud_direct_download_url(
    auth_token: str,
    file_id: str,
    *,
    api_host: str = "api.pcloud.com",
    timeout: int = 30,
) -> tuple[str | None, str | None]:
    """
    Вызывает pCloud getfilelink и собирает прямой HTTPS URL на CDN pCloud.

    Документация: метод getfilelink, параметры auth и fileid.
    Ответ: result==0, path, hosts[] → https://{hosts[0]}{path}
    """
    auth = (auth_token or "").strip()
    fid = str(file_id or "").strip()
    if not auth or not fid:
        return None, "missing_pcloud_auth_or_fileid"

    host = _normalize_api_host(api_host)
    base = f"https://{host}/getfilelink"
    try:
        r = requests.get(
            base,
            params={"auth": auth, "fileid": fid},
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.warning("pCloud getfilelink network error: %s", e)
        return None, "pcloud_getfilelink_network"

    try:
        data: dict[str, Any] = r.json()
    except ValueError:
        logger.warning("pCloud getfilelink non-JSON, HTTP %s", r.status_code)
        return None, "pcloud_getfilelink_bad_json"

    if int(data.get("result", -1)) != 0:
        err = str(data.get("error") or data.get("errormsg") or "unknown")
        logger.warning(
            "pCloud getfilelink failed result=%s error=%s (HTTP %s)",
            data.get("result"),
            err[:200],
            r.status_code,
        )
        return None, f"pcloud_getfilelink_result_{data.get('result')}:{err[:120]}"

    hosts = data.get("hosts") or []
    path = str(data.get("path") or "").strip()
    if not isinstance(hosts, list) or not hosts or not path:
        logger.warning("pCloud getfilelink missing hosts or path: %s", data)
        return None, "pcloud_getfilelink_missing_hosts_or_path"

    h0 = str(hosts[0]).strip()
    if not h0:
        return None, "pcloud_empty_host"
    if h0.startswith("http://") or h0.startswith("https://"):
        origin = h0.rstrip("/")
    else:
        origin = f"https://{h0}"
    if not path.startswith("/"):
        path = "/" + path
    # path уже может быть percent-encoded от API
    dl = f"{origin}{path}"
    return dl, None
