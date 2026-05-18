"""
Синхронизация переменных Railway (GraphQL): shared или несколько service id + redeploy web.

Используется для TESTIMONIALS_JSON после Save review в боте.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import request as urlrequest
from urllib.error import URLError

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"


def _sync_flag_enabled(flag: str) -> bool:
    return (os.environ.get(flag) or "").strip() == "1"


def _railway_api_token() -> str:
    return (os.environ.get("RAILWAY_API_TOKEN") or "").strip()


def _railway_project_id() -> str:
    return (os.environ.get("RAILWAY_PROJECT_ID") or "").strip()


def _railway_environment_id() -> str:
    return (os.environ.get("RAILWAY_ENVIRONMENT_ID") or "").strip()


def railway_credentials_configured() -> bool:
    return bool(_railway_api_token() and _railway_project_id() and _railway_environment_id())


def railway_variable_writes_allowed() -> bool:
    """
    Запись в Railway Variables через API — только worker (бот), не web при старте.

    На сервисе web: RAILWAY_VARIABLE_WRITES=0 или не задавать ENABLE_*_RAILWAY_SYNC / RAILWAY_API_TOKEN.
    На worker: RAILWAY_VARIABLE_WRITES=1 (или имя сервиса содержит worker/bot).
    """
    explicit = (os.environ.get("RAILWAY_VARIABLE_WRITES") or "").strip().lower()
    if explicit in ("0", "false", "no"):
        return False
    if explicit in ("1", "true", "yes"):
        return True
    svc = (os.environ.get("RAILWAY_SERVICE_NAME") or "").strip().lower()
    if not svc:
        return True
    if "web" in svc and "worker" not in svc and "bot" not in svc:
        return False
    return True


def railway_use_shared_variables() -> bool:
    """Shared Variables (без serviceId в API) — одна переменная на весь проект."""
    return (os.environ.get("RAILWAY_USE_SHARED_VARIABLES") or "").strip() == "1"


def collect_railway_service_ids_for_sync() -> list[str]:
    """
    Список service id для записи переменных (если не shared).
    RAILWAY_SYNC_SERVICE_IDS=id1,id2 или RAILWAY_SERVICE_ID + RAILWAY_WEB_SERVICE_ID.
    """
    raw = (os.environ.get("RAILWAY_SYNC_SERVICE_IDS") or "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    ids: list[str] = []
    for key in ("RAILWAY_SERVICE_ID", "RAILWAY_WEB_SERVICE_ID"):
        val = (os.environ.get(key) or "").strip()
        if val and val not in ids:
            ids.append(val)
    return ids


def railway_web_service_id() -> str:
    return (os.environ.get("RAILWAY_WEB_SERVICE_ID") or "").strip()


def testimonials_railway_redeploy_web_enabled() -> bool:
    """После обновления TESTIMONIALS_JSON перезапустить web (подхватить env). По умолчанию включено."""
    raw = (os.environ.get("ENABLE_TESTIMONIALS_RAILWAY_REDEPLOY_WEB") or "").strip()
    if raw == "0":
        return False
    return True


def _graphql_request(query: str, variables: dict[str, Any]) -> dict[str, Any] | None:
    token = _railway_api_token()
    if not token:
        return None
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urlrequest.Request(
        _GRAPHQL_URL,
        method="POST",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("errors"):
                logger.warning("Railway GraphQL errors: %s", parsed.get("errors"))
                return None
            return parsed if isinstance(parsed, dict) else None
    except (URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Railway GraphQL request failed: %s", exc)
        return None


def upsert_railway_variables(
    variables: list[dict[str, str]],
    *,
    service_id: str | None,
) -> bool:
    """Записать переменные в Railway (один service или shared без service_id)."""
    if not railway_credentials_configured():
        return False
    inp: dict[str, Any] = {
        "projectId": _railway_project_id(),
        "environmentId": _railway_environment_id(),
        "variables": variables,
    }
    if service_id:
        inp["serviceId"] = service_id
    query = """
    mutation UpsertVars($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input) { id }
    }
    """
    result = _graphql_request(query, {"input": inp})
    return result is not None


def upsert_railway_variable_to_targets(name: str, value: str) -> int:
    """
    Записать одну переменную: shared ИЛИ в каждый service из списка.
    Возвращает число успешных операций (0 = ничего не записано).
    """
    payload = [{"name": name, "value": value}]
    if railway_use_shared_variables():
        if upsert_railway_variables(payload, service_id=None):
            logger.info("Railway: upserted shared variable %s", name)
            return 1
        return 0
    targets = collect_railway_service_ids_for_sync()
    if not targets:
        logger.warning("Railway sync: no service ids (set RAILWAY_WEB_SERVICE_ID + RAILWAY_SERVICE_ID)")
        return 0
    ok = 0
    for sid in targets:
        if upsert_railway_variables(payload, service_id=sid):
            logger.info("Railway: upserted %s on service %s", name, sid[:8])
            ok += 1
    return ok


def redeploy_railway_service(service_id: str) -> bool:
    """Перезапуск сервиса (web подхватывает новый TESTIMONIALS_JSON из env)."""
    if not service_id or not railway_credentials_configured():
        return False
    query = """
    mutation Redeploy($environmentId: String!, $serviceId: String!) {
      serviceInstanceRedeploy(environmentId: $environmentId, serviceId: $serviceId)
    }
    """
    result = _graphql_request(
        query,
        {"environmentId": _railway_environment_id(), "serviceId": service_id},
    )
    if result is not None:
        logger.info("Railway: redeploy requested for service %s", service_id[:8])
    return result is not None


def sync_testimonials_json_to_railway(payload: str) -> None:
    """После save_testimonials на worker: TESTIMONIALS_JSON + опционально redeploy web."""
    if not _sync_flag_enabled("ENABLE_TESTIMONIALS_RAILWAY_SYNC"):
        return
    if not railway_variable_writes_allowed():
        return
    if not railway_credentials_configured():
        logger.warning("ENABLE_TESTIMONIALS_RAILWAY_SYNC=1 but Railway API ids/token missing")
        return
    n = upsert_railway_variable_to_targets("TESTIMONIALS_JSON", payload)
    if n < 1:
        return
    if testimonials_railway_redeploy_web_enabled():
        web_id = railway_web_service_id()
        if web_id:
            redeploy_railway_service(web_id)
        else:
            logger.warning(
                "TESTIMONIALS_JSON synced but RAILWAY_WEB_SERVICE_ID unset — "
                "web will not reload until manual redeploy"
            )
