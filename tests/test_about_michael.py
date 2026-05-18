"""Тесты портретов About Michael."""

from pathlib import Path

from music_sales.about_michael import (
    ABOUT_MICHAEL_PHOTO_2_REL,
    ABOUT_MICHAEL_PHOTO_REL,
    ABOUT_MICHAEL_VIDEO_REL,
    existing_about_michael_photos,
    existing_about_michael_video,
)


def test_existing_about_michael_video(tmp_path):
    video = tmp_path / ABOUT_MICHAEL_VIDEO_REL
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")
    assert existing_about_michael_video(tmp_path) == video
    assert existing_about_michael_video(tmp_path / "missing") is None


def test_existing_about_michael_photos_finds_both(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "about-michael.png").write_bytes(b"1")
    (assets / "about-michael-2.png").write_bytes(b"2")
    found = existing_about_michael_photos(tmp_path)
    assert [p.name for p in found] == ["about-michael.png", "about-michael-2.png"]


def test_existing_about_michael_photos_skips_missing_second(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "about-michael.png").write_bytes(b"1")
    found = existing_about_michael_photos(tmp_path)
    assert len(found) == 1
    assert found[0] == tmp_path / ABOUT_MICHAEL_PHOTO_REL


def test_repo_has_second_portrait_file():
    root = Path(__file__).resolve().parent.parent
    assert (root / ABOUT_MICHAEL_PHOTO_2_REL).is_file()
