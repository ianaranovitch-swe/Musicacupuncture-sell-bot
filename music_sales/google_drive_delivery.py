"""
Серверная выдача MP3 через Google Drive API (Service Account).

Ссылку Drive покупателю не отдаём: только стрим с Railway после проверки Stripe.
Файлы в Drive должны быть расшарены на email сервисного аккаунта (роль Viewer).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from music_sales import config

logger = logging.getLogger(__name__)

_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
_drive_service: Any | None = None


def _credentials_from_env() -> Any | None:
    """
    Service Account: путь к JSON-файлу или сам JSON одной строкой (удобно для Railway Variables).
    """
    raw = (config.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
    except ImportError as e:
        logger.error("Google API libraries missing: %s", e)
        return None

    if raw.startswith("{"):
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: %s", e)
            return None
        if not isinstance(info, dict):
            return None
        try:
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=list(_DRIVE_SCOPES),
            )
        except Exception as e:
            logger.exception("Invalid service account JSON in env: %s", e)
            return None

    p = Path(raw)
    if not p.is_absolute():
        from music_sales.catalog import project_root

        p = project_root() / raw
    if not p.is_file():
        logger.error("GOOGLE_SERVICE_ACCOUNT_JSON file not found: %s", raw[:120])
        return None
    try:
        return service_account.Credentials.from_service_account_file(
            str(p),
            scopes=list(_DRIVE_SCOPES),
        )
    except Exception as e:
        logger.exception("Failed to load service account file %s: %s", p, e)
        return None


def service_account_client_email() -> str | None:
    """Email для Share в Google Drive (подсказка в логах при 403)."""
    creds = _credentials_from_env()
    if not creds:
        return None
    return str(getattr(creds, "service_account_email", None) or "").strip() or None


def get_drive_service() -> Any | None:
    """Ленивая инициализация Drive API v3 (googleapiclient)."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    creds = _credentials_from_env()
    if not creds:
        return None

    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        logger.error("googleapiclient missing: %s", e)
        return None

    try:
        _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return _drive_service
    except Exception as e:
        logger.exception("Failed to build Drive service: %s", e)
        return None


def drive_file_metadata(file_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """Метаданные файла (name, size) — для HEAD и Content-Length."""
    fid = (file_id or "").strip()
    if not fid:
        return None, "missing_file_id"

    service = get_drive_service()
    if not service:
        return None, "drive_service_unavailable"

    try:
        meta = (
            service.files()
            .get(fileId=fid, fields="id,name,size,mimeType", supportsAllDrives=True)
            .execute()
        )
        return meta, None
    except Exception as e:
        logger.warning("Drive metadata failed file_id=%s: %s", fid, e)
        sa = service_account_client_email()
        if sa:
            logger.warning("Share the MP3 folder with this service account (Viewer): %s", sa)
        return None, f"drive_metadata:{type(e).__name__}"


def iter_drive_file_chunks(
    file_id: str,
    *,
    chunk_size: int = 256 * 1024,
) -> tuple[Iterator[bytes] | None, str | None]:
    """
    Поток байтов через Drive API alt=media (без публичной ссылки в браузере).
    """
    fid = (file_id or "").strip()
    if not fid:
        return None, "missing_file_id"

    creds = _credentials_from_env()
    if not creds:
        return None, "drive_service_unavailable"

    try:
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        return None, "google_libs_missing"

    try:
        session = AuthorizedSession(creds)
        url = f"https://www.googleapis.com/drive/v3/files/{fid}"
        resp = session.get(
            url,
            params={"alt": "media", "supportsAllDrives": "true"},
            stream=True,
            timeout=(30, 7200),
        )
    except Exception as e:
        logger.warning("Drive stream open failed file_id=%s: %s", fid, e)
        return None, f"drive_stream_open:{type(e).__name__}"

    if resp.status_code != 200:
        try:
            peek = (resp.text or "")[:300]
        except Exception:
            peek = ""
        resp.close()
        logger.warning("Drive alt=media HTTP %s file_id=%s body=%r", resp.status_code, fid, peek)
        if resp.status_code in (403, 404):
            sa = service_account_client_email()
            if sa:
                logger.warning(
                    "Drive %s: share file/folder with service account email (Viewer): %s",
                    resp.status_code,
                    sa,
                )
        return None, f"drive_http_{resp.status_code}"

    def _gen() -> Iterator[bytes]:
        try:
            for block in resp.iter_content(chunk_size=chunk_size):
                if block:
                    yield block
        finally:
            resp.close()

    return _gen(), None
