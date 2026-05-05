"""Общие фикстуры: изолировать тесты от локального .env (TEST_MODE и т.д.)."""

import pytest


@pytest.fixture(autouse=True)
def _clear_test_mode_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чтобы локальный .env с TEST_MODE=true не ломал ожидания по ценам и Stripe."""
    monkeypatch.delenv("TEST_MODE", raising=False)
