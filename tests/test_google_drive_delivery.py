"""Тесты Google Drive delivery (без реального API)."""

import json
from unittest.mock import MagicMock, patch


def test_iter_drive_file_chunks_yields_bytes(mocker, tmp_path):
    cred = tmp_path / "sa.json"
    cred.write_text('{"type":"service_account"}', encoding="utf-8")
    mocker.patch("music_sales.google_drive_delivery.config.GOOGLE_SERVICE_ACCOUNT_JSON", str(cred))

    class _Resp:
        status_code = 200

        def iter_content(self, chunk_size=None):
            yield b"abc"
            yield b"def"

        def close(self):
            pass

    mock_session = MagicMock()
    mock_session.get.return_value = _Resp()

    with patch("google.oauth2.service_account.Credentials.from_service_account_file"):
        with patch("google.auth.transport.requests.AuthorizedSession", return_value=mock_session):
            from music_sales.google_drive_delivery import iter_drive_file_chunks

            it, err = iter_drive_file_chunks("file123")
    assert err is None
    assert b"".join(list(it)) == b"abcdef"


def test_credentials_from_inline_json(mocker):
    """Railway Variables: GOOGLE_SERVICE_ACCOUNT_JSON как одна строка JSON."""
    inline = json.dumps(
        {
            "type": "service_account",
            "project_id": "p",
            "private_key_id": "k",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n",
            "client_email": "bot@p.iam.gserviceaccount.com",
            "client_id": "1",
        }
    )
    mocker.patch("music_sales.google_drive_delivery.config.GOOGLE_SERVICE_ACCOUNT_JSON", inline)
    with patch("google.oauth2.service_account.Credentials.from_service_account_info") as mock_info:
        from music_sales.google_drive_delivery import _credentials_from_env

        _credentials_from_env()
    mock_info.assert_called_once()


def test_builtin_tracks_have_google_drive_ids():
    import tracks

    tracks.reload_track_catalog()
    for tid, expected in tracks._BUILTIN_GOOGLE_DRIVE_IDS.items():
        row = next((t for t in tracks.TRACKS if int(t["id"]) == tid), None)
        assert row is not None, f"missing track id {tid}"
        assert row.get("google_drive_file_id") == expected
