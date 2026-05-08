"""Тесты отрисовки обложек бесплатного трека для Telegram."""

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from music_sales.free_track_cover_render import render_free_track_cover_for_telegram


def _write_rgb_png(path: Path, w: int, h: int, color: tuple[int, int, int]) -> None:
    from PIL import Image

    img = Image.new("RGB", (w, h), color)
    img.save(path, format="PNG")


def test_render_case_square_produces_png(tmp_path: Path) -> None:
    src = tmp_path / "b.png"
    _write_rgb_png(src, 120, 80, (10, 200, 90))
    data = render_free_track_cover_for_telegram(src, "case_square", output_size=64)
    assert data is not None
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_missing_file_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "nope.png"
    assert render_free_track_cover_for_telegram(missing, "case_square") is None


def test_unknown_style_returns_none(tmp_path: Path) -> None:
    src = tmp_path / "x.png"
    _write_rgb_png(src, 10, 10, (1, 2, 3))
    assert render_free_track_cover_for_telegram(src, "cd_round") is None
