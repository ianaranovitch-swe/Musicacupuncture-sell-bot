"""Тесты формата длительности трека для Mini App / бота."""

import pytest

from music_sales.mp3_duration import format_duration_short


@pytest.mark.parametrize(
    "sec,expected",
    [
        (None, None),
        (-1, None),
        (0, "0s"),
        (8, "8s"),
        (60, "1m"),
        (61, "1m 1s"),
        (3008, "50m 8s"),
        (3600, "1h"),
        (3661, "1h 1m 1s"),
        (7200, "2h"),
        (7325, "2h 2m 5s"),
    ],
)
def test_format_duration_short(sec: int | None, expected: str | None) -> None:
    assert format_duration_short(sec) == expected
