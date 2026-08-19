"""Общие фикстуры: изолировать тесты от локального .env (TEST_MODE и т.д.)."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clear_test_mode_for_tests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Чтобы локальный .env с TEST_MODE=true не ломал ожидания по ценам и Stripe."""
    monkeypatch.delenv("TEST_MODE", raising=False)
    # create_app читает os.environ["MINIAPP_CORS_ORIGINS"] раньше config — иначе .env ломает CORS-тесты.
    monkeypatch.delenv("MINIAPP_CORS_ORIGINS", raising=False)
    # Локальный sales_log.json >32 KB: Windows не даёт записать его в SALES_LOG_JSON.
    monkeypatch.setenv("SALES_LOG_JSON", "[]")
    monkeypatch.setattr(
        "music_sales.sales_log._sales_path",
        lambda: tmp_path / "sales_log.json",
    )
