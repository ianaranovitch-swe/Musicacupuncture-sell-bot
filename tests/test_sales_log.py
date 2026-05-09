"""Проверка структуры sales_log и резервной загрузки из SALES_LOG_JSON."""

from __future__ import annotations

import json


def test_append_sale_event_has_detailed_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("SALES_LOG_JSON", raising=False)
    from music_sales.sales_log import append_sale_event, read_sales_entries

    append_sale_event(
        song_id="heart_song",
        track_id=3,
        track_title="Divine sound Heart from God",
        amount=16.0,
        currency="USD",
        session_id="cs_test_123",
        transaction_id="pi_test_777",
        telegram_id=123456789,
    )
    rows = read_sales_entries()
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "sale"
    assert row["track_id"] == 3
    assert row["track_title"] == "Divine sound Heart from God"
    assert row["amount"] == 16.0
    assert row["currency"] == "USD"
    assert row["transaction_id"] == "pi_test_777"
    assert row["telegram_user_id"] == 123456789
    assert isinstance(row["week"], int)
    assert isinstance(row["month"], int)
    assert isinstance(row["year"], int)
    assert row["date"]
    assert row["time"]


def test_read_sales_entries_fallback_to_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    payload = json.dumps([{"event_type": "sale", "track_title": "X", "amount": 1.0, "currency": "USD"}])
    monkeypatch.setenv("SALES_LOG_JSON", payload)
    from music_sales.sales_log import read_sales_entries

    rows = read_sales_entries()
    assert len(rows) == 1
    assert rows[0]["track_title"] == "X"


def test_append_free_download_event(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("SALES_LOG_JSON", raising=False)
    from music_sales.sales_log import append_free_download_event, read_sales_entries

    append_free_download_event(telegram_user_id=42, track_title="Divine sound Super Feng Shui from God")
    rows = read_sales_entries()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "free_download"
    assert rows[0]["telegram_user_id"] == 42
