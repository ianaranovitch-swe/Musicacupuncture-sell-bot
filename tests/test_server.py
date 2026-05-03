from unittest.mock import MagicMock

_TEST_CATALOG = {
    "song1": {"name": "Relaxing Sound", "price_usd": 16, "file": "songs/song1.mp3"},
}


def test_create_checkout_returns_stripe_url(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)

    from music_sales.server import create_app

    app = create_app(
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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
        bot=mocker.Mock(),
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

    mock_bot = MagicMock()
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

    from music_sales.server import create_app

    app = create_app(
        bot=mock_bot,
        stripe_secret="sk_test_fake",
        project_root_override=tmp_path,
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/webhook", json=event)

    assert resp.status_code == 200
    mock_bot.send_audio.assert_called_once()
    kwargs = mock_bot.send_audio.call_args[1]
    assert kwargs["chat_id"] == 555
    assert kwargs["title"] == "Relaxing Sound"


def test_webhook_ignores_other_events(mocker, tmp_path):
    mocker.patch("stripe.Event.construct_from", return_value={"type": "charge.succeeded"})
    mock_bot = MagicMock()

    from music_sales.server import create_app

    app = create_app(
        bot=mock_bot,
        stripe_secret="sk_test_fake",
        project_root_override=tmp_path,
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/webhook", json={})

    assert resp.status_code == 200
    mock_bot.send_audio.assert_not_called()


def test_success_and_cancel_pages():
    from music_sales.server import create_app

    app = create_app(
        bot=MagicMock(),
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
        bot=MagicMock(),
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
        bot=MagicMock(),
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
        bot=MagicMock(),
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
        bot=MagicMock(),
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["ready"] is False
