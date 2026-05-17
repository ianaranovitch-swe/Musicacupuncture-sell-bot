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


def test_client_email_from_env_when_credentials_fail_to_load(mocker):
    """Битый private_key — Credentials None, но client_email всё равно в подсказке."""
    inline = json.dumps(
        {
            "type": "service_account",
            "project_id": "p",
            "private_key": "not-a-valid-key",
            "client_email": "hint-me@my-project.iam.gserviceaccount.com",
            "client_id": "1",
        }
    )
    mocker.patch("music_sales.google_drive_delivery.config.GOOGLE_SERVICE_ACCOUNT_JSON", inline)
    with patch("google.oauth2.service_account.Credentials.from_service_account_info", side_effect=ValueError("bad key")):
        from music_sales.google_drive_delivery import (
            drive_credentials_available,
            service_account_client_email,
        )

        assert drive_credentials_available() is False
        assert service_account_client_email() == "hint-me@my-project.iam.gserviceaccount.com"


def test_client_email_from_missing_file_path(mocker, tmp_path):
    mocker.patch(
        "music_sales.google_drive_delivery.config.GOOGLE_SERVICE_ACCOUNT_JSON",
        "secrets/missing-sa.json",
    )
    from music_sales.google_drive_delivery import drive_credentials_available, service_account_client_email

    assert drive_credentials_available() is False
    assert service_account_client_email() is None


def test_credentials_from_inline_json(mocker):
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
        from music_sales.google_drive_delivery import drive_credentials_available

        assert drive_credentials_available() is True
    mock_info.assert_called_once()


def test_builtin_tracks_have_google_drive_ids():
    import tracks

    tracks.reload_track_catalog()
    for tid, expected in tracks._BUILTIN_GOOGLE_DRIVE_IDS.items():
        row = next((t for t in tracks.TRACKS if int(t["id"]) == tid), None)
        assert row is not None, f"missing track id {tid}"
        assert row.get("google_drive_file_id") == expected
