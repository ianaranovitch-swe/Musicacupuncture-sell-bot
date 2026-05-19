"""Тесты подтягивания sales log с web на worker."""

import json

from music_sales.sales_log_pull import fetch_web_sales_log_snapshot, pull_sales_log_from_web


def test_fetch_web_sales_log_snapshot(monkeypatch):
    monkeypatch.setenv("SALES_LOG_PULL_SECRET", "sec")
    monkeypatch.setenv("WEB_PUBLIC_URL", "https://example.com")

    class _Resp:
        def read(self):
            return json.dumps({"entries": [{"event_type": "free_download", "ts": "1"}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=20: _Resp())
    rows = fetch_web_sales_log_snapshot()
    assert len(rows) == 1


def test_pull_sales_log_from_web_merges(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "worker")
    monkeypatch.delenv("ENABLE_SALES_LOG_RAILWAY_SYNC", raising=False)
    monkeypatch.setattr(
        "music_sales.sales_log_pull.fetch_web_sales_log_snapshot",
        lambda: [
            {
                "event_type": "free_download",
                "ts": "2026-05-20T12:00:00+00:00",
                "track_title": "Divine sound Super Feng Shui from God",
                "source": "website",
            }
        ],
    )
    n = pull_sales_log_from_web()
    assert n >= 0
    from music_sales.sales_log import count_free_gift_downloads, read_sales_entries

    assert count_free_gift_downloads(read_sales_entries()) >= 1
