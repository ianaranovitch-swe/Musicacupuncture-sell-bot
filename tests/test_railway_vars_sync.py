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


def test_web_service_name_blocks_variable_writes(monkeypatch):
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "musicacupuncture-web")
    monkeypatch.delenv("RAILWAY_VARIABLE_WRITES", raising=False)
    assert rvs.railway_variable_writes_allowed() is False


def test_worker_service_name_allows_variable_writes(monkeypatch):
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "sell-bot-worker")
    monkeypatch.delenv("RAILWAY_VARIABLE_WRITES", raising=False)
    assert rvs.railway_variable_writes_allowed() is True


def test_sales_log_writes_allowed_on_web_with_sync(monkeypatch):
    monkeypatch.setenv("ENABLE_SALES_LOG_RAILWAY_SYNC", "1")
    monkeypatch.setenv("RAILWAY_API_TOKEN", "tok")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "musicacupuncture-web")
    monkeypatch.setenv("RAILWAY_VARIABLE_WRITES", "0")
    assert rvs.railway_sales_log_writes_allowed() is True
    assert rvs.railway_variable_writes_allowed() is False


def test_read_sales_entries_merges_railway_json(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("SALES_LOG_JSON", raising=False)
    monkeypatch.setenv("ENABLE_SALES_LOG_RAILWAY_SYNC", "1")
    monkeypatch.setenv("RAILWAY_API_TOKEN", "tok")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
    remote = json.dumps(
        [
            {
                "event_type": "free_download",
                "ts": "2026-05-20T12:00:00+00:00",
                "track_title": "Divine sound Super Feng Shui from God",
                "source": "website",
            }
        ]
    )
    monkeypatch.setattr(
        rvs,
        "fetch_railway_variable_value",
        lambda name: remote if name == "SALES_LOG_JSON" else "",
    )
    from music_sales.sales_log import read_sales_entries, count_free_gift_downloads

    rows = read_sales_entries()
    assert count_free_gift_downloads(rows) == 1


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
