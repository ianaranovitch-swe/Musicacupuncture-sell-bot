"""Тесты сопоставления трека с ключами FILE_IDS_JSON."""

from music_sales.file_id_delivery import file_id_for_song


def test_file_id_prefers_stem_from_file_path():
    song = {"name": "Display Name", "file": "songs/My Track File.mp3", "price_usd": 16}
    ids = {"My Track File": "fid_stem", "Display Name": "fid_name"}
    assert file_id_for_song(song, ids) == "fid_stem"


def test_file_id_falls_back_to_name():
    song = {"name": "Only By Name", "file": "songs/x.mp3", "price_usd": 16}
    ids = {"Only By Name": "fid_n"}
    assert file_id_for_song(song, ids) == "fid_n"
