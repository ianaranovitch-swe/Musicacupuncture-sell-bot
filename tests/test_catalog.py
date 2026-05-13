from music_sales.catalog import (
    discover_songs,
    song_path,
    stripe_unit_amount_ore,
    unit_amount_for_song,
)


def test_discover_songs_reads_audio_files(monkeypatch, tmp_path):
    songs_dir = tmp_path / "songs"
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
        assert song["file"].startswith("songs/")
        assert unit_amount_for_song(song) == stripe_unit_amount_ore(sid)


def test_discover_songs_uses_test_price_when_test_mode(monkeypatch, tmp_path):
    """При TEST_MODE цена в каталоге берётся из TEST_PRICE_USD (для Stripe / подписей)."""
    songs_dir = tmp_path / "songs"
    songs_dir.mkdir()
    (songs_dir / "alpha.mp3").write_bytes(b"x")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("TEST_MODE", "true")
    monkeypatch.setenv("TEST_PRICE_USD", "1")

    found = discover_songs()
    assert len(found) == 1
    assert next(iter(found.values()))["price_usd"] == 1


def test_song_path_joins_project_root(monkeypatch, tmp_path):
    songs_dir = tmp_path / "songs"
    songs_dir.mkdir()
    (songs_dir / "song1.mp3").write_bytes(b"x")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))

    p = song_path("song1")
    assert p.name == "song1.mp3"
    assert "songs" in p.parts


def test_resolve_song_id_by_audio_stem_fallback_from_tracks(monkeypatch, tmp_path):
    """Без папки songs/ на диске — stem всё раже находим через tracks.py (как на Railway)."""
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    from music_sales.catalog import resolve_song_id_by_audio_stem

    stem = "Divine sound Estrogen from God"
    assert resolve_song_id_by_audio_stem(stem) == "Divine_sound_Estrogen_from_God"


def test_synthetic_song_row_for_song_id(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    from music_sales.catalog import synthetic_song_row_for_song_id

    row = synthetic_song_row_for_song_id("Divine_sound_Estrogen_from_God")
    assert row is not None
    assert row["file"].startswith("songs/")
    assert "Estrogen" in row["name"]


def test_tracks_reload_applies_test_payment_link(monkeypatch):
    import tracks

    monkeypatch.setenv("TEST_MODE", "true")
    monkeypatch.setenv("TEST_PAYMENT_LINK", "https://buy.stripe.com/test_abc123")
    tracks.reload_track_catalog()
    try:
        paid = [t for t in tracks.TRACKS if str(t.get("price", "")).strip().upper() != "FREE"]
        assert paid
        for t in paid:
            assert t["buy_url"] == "https://buy.stripe.com/test_abc123"
            assert t["buy_url_sek"] == "https://buy.stripe.com/test_abc123"
        free = [t for t in tracks.TRACKS if str(t.get("price", "")).strip().upper() == "FREE"]
        assert free
        assert not (free[0].get("buy_url") or "").strip()
    finally:
        monkeypatch.delenv("TEST_MODE", raising=False)
        monkeypatch.delenv("TEST_PAYMENT_LINK", raising=False)
        tracks.reload_track_catalog()
