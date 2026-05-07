"""Тесты /health и build_health_report."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_cmd_health_denied_for_non_owner(mocker):
    mocker.patch("music_sales.health_report.config.health_command_allowed_user_ids", return_value={999, 7973899604})
    from music_sales.health_report import cmd_health

    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 1
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await cmd_health(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "This command is only for the bot owner or the developer."
    )


@pytest.mark.asyncio
async def test_cmd_health_owner_receives_html(mocker):
    mocker.patch("music_sales.health_report.config.health_command_allowed_user_ids", return_value={42, 7973899604})
    mocker.patch(
        "music_sales.health_report.build_health_report",
        return_value={
            "ready": True,
            "expected_tracks": 16,
            "missing_audio_from_tracks_py": [],
            "missing_covers_from_tracks_py": [],
            "discovered_mp3_count": 16,
            "songs_folder_exists": True,
            "checks": {
                "stripe": {"ok": True, "detail": "ok"},
                "backend_options": {"ok": True, "detail": "ok"},
                "miniapp_url": {"ok": True, "detail": "ok"},
                "miniapp_cors": {"ok": True, "detail": "ok"},
            },
        },
    )
    from music_sales.health_report import cmd_health

    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 42
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot", id=7))

    await cmd_health(update, context)

    assert update.message.reply_text.await_count == 1
    kwargs = update.message.reply_text.call_args.kwargs
    assert kwargs.get("parse_mode") == "HTML"
    assert "Health report" in (update.message.reply_text.call_args.args[0] or "")


@pytest.mark.asyncio
async def test_cmd_health_developer_id_allowed(mocker):
    """Разработчик (7973899604 по умолчанию в config) может вызывать /health, даже если владелец другой."""
    mocker.patch("music_sales.health_report.config.health_command_allowed_user_ids", return_value={111, 7973899604})
    mocker.patch(
        "music_sales.health_report.build_health_report",
        return_value={
            "ready": True,
            "expected_tracks": 16,
            "missing_audio_from_tracks_py": [],
            "missing_covers_from_tracks_py": [],
            "discovered_mp3_count": 16,
            "songs_folder_exists": True,
            "checks": {"stripe": {"ok": True, "detail": "ok"}},
        },
    )
    from music_sales.health_report import cmd_health

    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 7973899604
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot.get_me = AsyncMock(return_value=MagicMock(username="x", id=1))

    await cmd_health(update, context)

    assert update.message.reply_text.await_count == 1


def test_build_health_report_one_track_all_files_present(mocker, tmp_path):
    fake_tracks = [
        {
            "id": 1,
            "audio": "songs/demo.mp3",
            "cover": "covers/demo.jpg",
        }
    ]
    mocker.patch("music_sales.health_report.TRACKS", fake_tracks)
    mocker.patch("music_sales.health_report.project_root", return_value=tmp_path)
    mocker.patch("music_sales.health_report.songs_dir", return_value=tmp_path / "songs")
    mocker.patch(
        "music_sales.health_report.discover_songs",
        return_value={"x": {"name": "Demo", "file": "songs/demo.mp3", "price_usd": 16}},
    )
    mocker.patch("music_sales.health_report._stripe_balance_ok", return_value=(True, "ok"))
    mocker.patch("music_sales.health_report._backend_options_ok", return_value=(True, "ok"))
    mocker.patch("music_sales.health_report._miniapp_env_ok", return_value=(True, "ok"))
    mocker.patch("music_sales.health_report._cors_configured", return_value=(True, "ok"))
    mocker.patch("music_sales.health_report._file_ids_json_ok", return_value=(True, "ok"))

    (tmp_path / "songs").mkdir()
    (tmp_path / "covers").mkdir()
    (tmp_path / "songs" / "demo.mp3").write_bytes(b"x")
    (tmp_path / "covers" / "demo.jpg").write_bytes(b"x")

    from music_sales.health_report import build_health_report

    r = build_health_report()
    assert "test_mode" in r
    assert r["missing_audio_from_tracks_py"] == []
    assert r["missing_covers_from_tracks_py"] == []
    assert r["extra_mp3_files_not_in_tracks_py"] == []
    assert r["discovered_mp3_count"] == 1
