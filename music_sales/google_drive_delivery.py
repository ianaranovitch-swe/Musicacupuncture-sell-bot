"""
Серверная выдача MP3 через Google Drive API (Service Account).

Ссылку Drive покупателю не отдаём: только стрим с Railway после проверки Stripe.
Файлы в Drive должны быть расшарены на email сервисного аккаунта (роль Viewer).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator

from music_sales import config

logger = logging.getLogger(__name__)

_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
_drive_service: Any | None = None


def _resolve_credentials_path() -> Path | None:
    raw = (config.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        from music_sales.catalog import project_root

        p = project_root() / raw
    if not p.is_file():
        logger.error("GOOGLE_SERVICE_ACCOUNT_JSON file not found: %s", raw)
        return None
    return p.resolve()


def get_drive_service() -> Any | None:
    """Ленивая инициализация Drive API v3 (googleapiclient)."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    cred_path = _resolve_credentials_path()
    if not cred_path:
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        logger.error("Google API libraries missing (pip install google-api-python-client google-auth): %s", e)
        return None

    try:
        creds = service_account.Credentials.from_service_account_file(
            str(cred_path),
            scopes=list(_DRIVE_SCOPES),
        )
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

    cred_path = _resolve_credentials_path()
    if not cred_path:
        return None, "drive_service_unavailable"

    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        return None, "google_libs_missing"

    try:
        creds = service_account.Credentials.from_service_account_file(
            str(cred_path),
            scopes=list(_DRIVE_SCOPES),
        )
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
        return None, f"drive_http_{resp.status_code}"

    def _gen() -> Iterator[bytes]:
        try:
            for block in resp.iter_content(chunk_size=chunk_size):
                if block:
                    yield block
        finally:
            resp.close()

    return _gen(), None
