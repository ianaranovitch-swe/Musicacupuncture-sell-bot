"""Тесты синхронизации переменных Railway."""

import json

from music_sales import railway_vars_sync as rvs


def test_collect_service_ids_from_two_env_vars(monkeypatch):
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "worker-1")
    monkeypatch.setenv("RAILWAY_WEB_SERVICE_ID", "web-2")
    monkeypatch.delenv("RAILWAY_SYNC_SERVICE_IDS", raising=False)
    assert rvs.collect_railway_service_ids_for_sync() == ["worker-1", "web-2"]


def test_upsert_shared_omits_service_id(monkeypatch):
    monkeypatch.setenv("RAILWAY_API_TOKEN", "tok")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
    monkeypatch.setenv("RAILWAY_USE_SHARED_VARIABLES", "1")
    captured: list[dict] = []

    def fake_graphql(query: str, variables: dict) -> dict:
        captured.append(variables)
        return {"data": {"variableCollectionUpsert": {"id": "x"}}}

    monkeypatch.setattr(rvs, "_graphql_request", fake_graphql)
    assert rvs.upsert_railway_variable_to_targets("TESTIMONIALS_JSON", "[{}]") == 1
    assert "serviceId" not in captured[0]["input"]


def test_upsert_dual_services(monkeypatch):
    monkeypatch.setenv("RAILWAY_API_TOKEN", "tok")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
    monkeypatch.setenv("RAILWAY_USE_SHARED_VARIABLES", "0")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "w")
    monkeypatch.setenv("RAILWAY_WEB_SERVICE_ID", "web")
    calls: list[str | None] = []

    def fake_graphql(query: str, variables: dict) -> dict:
        calls.append(variables["input"].get("serviceId"))
        return {"data": {}}

    monkeypatch.setattr(rvs, "_graphql_request", fake_graphql)
    assert rvs.upsert_railway_variable_to_targets("TESTIMONIALS_JSON", "[]") == 2
    assert calls == ["w", "web"]


def test_sync_testimonials_triggers_redeploy_web(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTIMONIALS_RAILWAY_SYNC", "1")
    monkeypatch.setenv("RAILWAY_API_TOKEN", "tok")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
    monkeypatch.setenv("RAILWAY_USE_SHARED_VARIABLES", "1")
    monkeypatch.setenv("RAILWAY_WEB_SERVICE_ID", "web-svc")
    redeployed: list[str] = []

    monkeypatch.setattr(rvs, "upsert_railway_variable_to_targets", lambda n, v: 1)
    monkeypatch.setattr(rvs, "redeploy_railway_service", lambda sid: redeployed.append(sid) or True)
    rvs.sync_testimonials_json_to_railway("[{}]")
    assert redeployed == ["web-svc"]
