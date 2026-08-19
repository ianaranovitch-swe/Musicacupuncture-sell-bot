"""Тесты GDRIVE_IDS_JSON и поиска Drive file_id для сайта."""

import json

import pytest


def test_load_gdrive_ids_merges_env_over_builtin(monkeypatch):
    import tracks

    monkeypatch.setenv(
        "GDRIVE_IDS_JSON",
        json.dumps({"Divine sound Heart from God": "override_from_env"}),
    )
    from music_sales.gdrive_ids import load_gdrive_ids_dict

    ids = load_gdrive_ids_dict()
    assert ids["Divine sound Heart from God"] == "override_from_env"
    assert ids.get("Divine sound Estrogen from God") == tracks._BUILTIN_GOOGLE_DRIVE_IDS[2]


def test_google_drive_file_id_for_song_by_stem():
    from music_sales.gdrive_ids import google_drive_file_id_for_song

    song = {"name": "Heart", "file": "songs/Divine sound Heart from God.mp3"}
    gid = google_drive_file_id_for_song(
        song,
        {"Divine sound Heart from God": "drive123"},
    )
    assert gid == "drive123"


def test_mozart_tracks_have_google_drive_ids():
    from music_sales.gdrive_ids import tracks_missing_google_drive_ids

    missing = tracks_missing_google_drive_ids()
    assert missing == []


def test_mozart_immune_drive_id_from_stem():
    import tracks
    from music_sales.gdrive_ids import google_drive_file_id_for_song

    gid = google_drive_file_id_for_song(
        {"name": "Mozart + Immune System + Stomach", "file": "songs/Mozart+Immune-System+Stomach.mp3"}
    )
    assert gid == tracks._BUILTIN_GOOGLE_DRIVE_IDS[24]


def test_song_requires_drive_for_website_mozart():
    from music_sales.gdrive_ids import song_requires_drive_for_website

    assert song_requires_drive_for_website(
        {"file": "songs/Mozart+Immune-System+Stomach.mp3", "name": "Mozart + Immune System + Stomach"}
    )
    assert not song_requires_drive_for_website(
        {"file": "songs/song1.mp3", "name": "Relaxing Sound"}
    )


def test_enrich_uses_gdrive_ids_json_when_no_builtin_on_row(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "GDRIVE_IDS_JSON",
        json.dumps({"Divine sound NO Alcohol from God": "env_only_id"}),
    )
    from music_sales.catalog import _song_id_from_stem, enrich_song_row_delivery_ids

    stem = "Divine sound NO Alcohol from God"
    sid = _song_id_from_stem(stem)
    row = {"name": stem, "file": f"songs/{stem}.mp3", "price_usd": 16}
    merged = enrich_song_row_delivery_ids(row, sid)
    assert merged.get("google_drive_file_id") == "env_only_id"
