from music_sales.catalog import (
    discover_songs,
    song_path,
    stripe_unit_amount_ore,
    unit_amount_for_song,
)


def test_discover_songs_reads_audio_files(monkeypatch, tmp_path):
    songs_dir = tmp_path / "SONGS"
    songs_dir.mkdir()
    (songs_dir / "alpha.mp3").write_bytes(b"x")
    (songs_dir / "beta.wav").write_bytes(b"y")

    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))

    found = discover_songs()
    assert len(found) == 2
    ids = set(found.keys())
    assert ids == {"alpha", "beta"}
    for sid, song in found.items():
        assert song["price_usd"] > 0
        assert song["file"].startswith("SONGS/")
        assert unit_amount_for_song(song) == stripe_unit_amount_ore(sid)


def test_song_path_joins_project_root(monkeypatch, tmp_path):
    songs_dir = tmp_path / "SONGS"
    songs_dir.mkdir()
    (songs_dir / "song1.mp3").write_bytes(b"x")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))

    p = song_path("song1")
    assert p.name == "song1.mp3"
    assert "SONGS" in p.parts
