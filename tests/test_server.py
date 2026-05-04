from unittest.mock import MagicMock

import pytest

_TEST_CATALOG = {
    "song1": {"name": "Relaxing Sound", "price_usd": 16, "file": "songs/song1.mp3"},
}


@pytest.fixture(autouse=True)
def _fake_bot_token_for_server_tests(mocker):
    # create_app читает config.BOT_TOKEN при старте; в CI/локально переменная часто пустая
    mocker.patch("music_sales.server.config.BOT_TOKEN", "123456789:FAKE-TOKEN-FOR-TESTS")


def test_create_checkout_returns_stripe_url(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        domain="http://localhost:5000",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"song_id": "song1", "telegram_id": 42})

    assert resp.status_code == 200
    assert resp.get_json()["url"] == "https://stripe.test/session"

    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert kwargs["line_items"][0]["price_data"]["currency"] == "usd"
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 1600
    assert kwargs["metadata"]["telegram_name"] == "Unknown user"
    assert kwargs["automatic_payment_methods"]["enabled"] is True


def test_create_checkout_accepts_selected_currency(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"song_id": "song1", "telegram_id": 42, "currency": "sek"})

    assert resp.status_code == 200
    kwargs = create.call_args.kwargs
    assert kwargs["line_items"][0]["price_data"]["currency"] == "sek"
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 16900


def test_create_checkout_accepts_track_id_when_resolved(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post(
        "/create-checkout",
        json={"track_id": 1, "telegram_id": 99, "telegram_name": "Test User", "currency": "usd"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["url"] == "https://stripe.test/session"
    meta = create.call_args.kwargs["metadata"]
    assert meta["telegram_id"] == "99"
    assert meta["song_id"] == "song1"


def test_create_checkout_track_id_401_when_secret_required_but_missing(mocker):
    mocker.patch("music_sales.config.MINIAPP_CHECKOUT_SECRET", "expected-secret")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"track_id": 1, "telegram_id": 1, "currency": "usd"})
    assert resp.status_code == 401


def test_create_checkout_options_preflight(mocker):
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://example.github.io")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.options(
        "/create-checkout",
        headers={"Origin": "https://example.github.io"},
    )
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://example.github.io"

    resp2 = client.options(
        "/create-payment",
        headers={"Origin": "https://example.github.io"},
    )
    assert resp2.status_code == 204
    assert resp2.headers.get("Access-Control-Allow-Origin") == "https://example.github.io"


def test_create_checkout_cors_accepts_trailing_slash_in_env(mocker):
    """В MINIAPP_CORS_ORIGINS часто добавляют / в конце — сравнение нормализуем."""
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://example.github.io/")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.options(
        "/create-payment",
        headers={"Origin": "https://example.github.io"},
    )
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://example.github.io"


def test_create_payment_post_same_as_checkout(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post(
        "/create-payment",
        json={"track_id": 1, "telegram_id": 99, "telegram_name": "Test User", "currency": "usd"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["url"] == "https://stripe.test/session"
    create.assert_called_once()


def test_create_checkout_400_when_missing_fields(mocker):
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"song_id": "song1"})
    assert resp.status_code == 400


def test_create_checkout_400_when_unknown_song(mocker):
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post(
        "/create-checkout", json={"song_id": "unknown", "telegram_id": 1}
    )
    assert resp.status_code == 400
    assert "Unknown" in resp.get_json().get("error", "")


def test_create_checkout_400_when_unsupported_currency(mocker):
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"song_id": "song1", "telegram_id": 1, "currency": "pln"})
    assert resp.status_code == 400


def test_webhook_completed_sends_audio(mocker, tmp_path):
    (tmp_path / "songs").mkdir()
    (tmp_path / "songs" / "song1.mp3").write_bytes(b"fake-audio")

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {
                    "telegram_id": "555",
                    "song_id": "song1",
                }
            }
        },
    }
    mocker.patch("stripe.Event.construct_from", return_value=event)
    mock_post = mocker.patch("music_sales.server.requests.post")
    mock_post.return_value.raise_for_status = MagicMock()

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        project_root_override=tmp_path,
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/webhook", json=event)

    assert resp.status_code == 200
    # The first requests.post call must be the sendAudio delivery
    assert mock_post.call_count >= 1
    send_audio_call = mock_post.call_args_list[0]
    assert "sendAudio" in send_audio_call.args[0]
    assert send_audio_call.kwargs["data"]["chat_id"] == 555
    assert send_audio_call.kwargs["data"]["title"] == "Relaxing Sound"


def test_webhook_ignores_other_events(mocker, tmp_path):
    mocker.patch("stripe.Event.construct_from", return_value={"type": "charge.succeeded"})
    mock_post = mocker.patch("music_sales.server.requests.post")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        project_root_override=tmp_path,
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/webhook", json={})

    assert resp.status_code == 200
    # No Telegram API calls should be made for unrecognised events
    send_audio_calls = [
        c for c in mock_post.call_args_list if "sendAudio" in (c.args[0] if c.args else "")
    ]
    assert send_audio_calls == []


def test_success_and_cancel_pages():
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    assert client.get("/success").status_code == 200
    assert client.get("/cancel").status_code == 200


def test_miniapp_html_route(mocker, tmp_path):
    (tmp_path / "miniapp.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get("/miniapp.html")
    assert resp.status_code == 200
    assert b"doctype html" in resp.data.lower()


def test_covers_route_serves_file(mocker, tmp_path):
    covers = tmp_path / "covers"
    covers.mkdir()
    (covers / "sample.jpg").write_bytes(b"\xff\xd8\xff")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    assert client.get("/covers/sample.jpg").status_code == 200
    assert client.get("/covers/../.env").status_code == 400


def test_covers_route_404_when_missing(mocker, tmp_path):
    (tmp_path / "covers").mkdir()
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    assert client.get("/covers/nope.jpg").status_code == 404


def test_health_http_route(mocker, tmp_path):
    mocker.patch(
        "music_sales.health_report.build_health_report",
        return_value={"ready": False, "checks": {}},
    )
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["ready"] is False
