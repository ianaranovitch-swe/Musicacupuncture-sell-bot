import json
import os
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


def test_create_checkout_cancel_url_https_when_domain_has_no_scheme(mocker):
    """Stripe: cancel_url must include scheme — bare host used to raise InvalidRequestError."""
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        domain="musicacupuncture.example",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"song_id": "song1", "telegram_id": 42})
    assert resp.status_code == 200
    kwargs = create.call_args.kwargs
    assert kwargs["cancel_url"] == "https://musicacupuncture.example/cancel"
    assert kwargs["success_url"] == "https://musicacupuncture.example/success"


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


def test_website_create_payment_success_url_follows_backend_without_hardcoded_domain(mocker, monkeypatch):
    """WEBSITE_SUCCESS_URL не задан — success_url = тот же origin, что cancel, + /website.html."""
    monkeypatch.delenv("WEBSITE_SUCCESS_URL", raising=False)
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)
    mocker.patch("music_sales.server.config.BACKEND_URL", "https://railway-backend.example")
    mocker.patch("music_sales.server.config.DOMAIN", "")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        domain="https://railway-backend.example",
    )
    client = app.test_client()
    resp = client.post("/website-create-payment", json={"track_id": 2, "currency": "usd"})
    assert resp.status_code == 200
    su = create.call_args.kwargs["success_url"]
    assert "railway-backend.example/website.html" in su
    assert "musicacupuncture.digital" not in su


def test_create_checkout_uses_custom_success_url_when_configured(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)
    mocker.patch("music_sales.config.CHECKOUT_SUCCESS_URL", "https://t.me/musicacupuncture_bot")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        domain="https://web.example",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/create-checkout", json={"song_id": "song1", "telegram_id": 42})

    assert resp.status_code == 200
    kwargs = create.call_args.kwargs
    assert kwargs["success_url"] == "https://t.me/musicacupuncture_bot"


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


def test_create_checkout_cors_accepts_full_page_url_in_env(mocker):
    """В env копируют полный URL Mini App — Origin всё равно только scheme+host."""
    mocker.patch(
        "music_sales.config.MINIAPP_CORS_ORIGINS",
        "https://user.github.io/repo-name/miniapp.html, https://other.example",
    )
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.options(
        "/create-payment",
        headers={"Origin": "https://user.github.io"},
    )
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://user.github.io"


def test_miniapp_pricing_get_and_cors(mocker):
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://pages.example")
    mocker.patch("music_sales.config.test_mode_active", return_value=False)
    mocker.patch(
        "music_sales.server._miniapp_track_durations_payload",
        return_value=[{"id": 2, "seconds": 3008, "label": "50m 8s"}],
    )
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    opt = client.options("/miniapp-pricing", headers={"Origin": "https://pages.example"})
    assert opt.status_code == 204
    assert opt.headers.get("Access-Control-Allow-Origin") == "https://pages.example"

    got = client.get("/miniapp-pricing", headers={"Origin": "https://pages.example"})
    assert got.status_code == 200
    body = got.get_json()
    assert body.get("test_mode") is False
    assert "$" in (body.get("usd_display") or "")
    assert body.get("track_durations") == [{"id": 2, "seconds": 3008, "label": "50m 8s"}]


def test_miniapp_pricing_test_mode_response(mocker):
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://t.example")
    mocker.patch("music_sales.config.test_mode_active", return_value=True)
    mocker.patch("music_sales.server._miniapp_track_durations_payload", return_value=[])
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    got = client.get("/miniapp-pricing", headers={"Origin": "https://t.example"})
    assert got.status_code == 200
    body = got.get_json()
    assert body.get("test_mode") is True
    assert body.get("usd_display") == "$1"
    assert "kr" in (body.get("sek_display") or "").lower()
    assert body.get("track_durations") == []


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


def test_website_create_payment_without_secret(mocker):
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")
    mocker.patch("music_sales.config.MINIAPP_CHECKOUT_SECRET", "super-secret")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.post("/website-create-payment", json={"track_id": 2, "currency": "sek"})

    assert resp.status_code == 200
    assert resp.get_json()["url"] == "https://stripe.test/session"
    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert kwargs["line_items"][0]["price_data"]["currency"] == "sek"


def test_website_create_payment_works_without_songs_folder(mocker, tmp_path, monkeypatch):
    """Railway без MP3 в репо: checkout всё раже строится из tracks.py + synthetic row."""
    mock_session = mocker.Mock()
    mock_session.url = "https://stripe.test/session"
    create = mocker.patch("stripe.checkout.Session.create", return_value=mock_session)
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=None,
    )
    client = app.test_client()
    resp = client.post("/website-create-payment", json={"track_id": 2, "currency": "usd"})
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
    mocker.patch.dict(
        os.environ,
        {"FILE_IDS_JSON": json.dumps({"song1": "telegram_doc_file_id_test"})},
        clear=False,
    )

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
    assert mock_post.call_count >= 1
    send_doc_call = mock_post.call_args_list[0]
    assert "sendDocument" in send_doc_call.args[0]
    assert send_doc_call.kwargs["data"]["chat_id"] == 555
    assert send_doc_call.kwargs["data"]["document"] == "telegram_doc_file_id_test"


def test_webhook_completed_website_source_skips_telegram_delivery(mocker, tmp_path):
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {
                    "telegram_id": "0",
                    "telegram_name": "Website customer",
                    "song_id": "song1",
                    "source": "website",
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
    urls = [c.args[0] for c in mock_post.call_args_list if c.args]
    assert all("sendDocument" not in u for u in urls)


def test_free_track_json_returns_file_url(tmp_path, mocker):
    """website.html: GET /free-track — url ведёт на тот же backend /free-track-file (прокси без токена в браузере)."""
    mocker.patch.dict(
        os.environ,
        {"FILE_IDS_JSON": json.dumps({"Divine sound Super Feng Shui from God": "dummy_file_id"})},
        clear=False,
    )
    mocker.patch(
        "music_sales.server.resolve_telegram_file_download_url",
        return_value=("https://api.telegram.org/file/botFAKE/music/test.mp3", None),
    )

    class _FakeUpstream:
        status_code = 200
        headers = {"Content-Length": "4"}
        closed = False

        def iter_content(self, chunk_size=None):
            yield b"\x00\x00\x00\x00"

        def close(self):
            self.closed = True

    fake_up = _FakeUpstream()
    mocker.patch("music_sales.server.requests.get", return_value=fake_up)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get("/free-track")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body and body.get("url")
    assert "/free-track-file" in (body.get("url") or "")
    assert "api.telegram.org" not in (body.get("url") or "")

    file_resp = client.get("/free-track-file", follow_redirects=False)
    assert file_resp.status_code == 200
    assert file_resp.mimetype == "audio/mpeg"
    assert file_resp.data == b"\x00\x00\x00\x00"  # съедаем стрим — иначе finally/close может не вызваться
    assert fake_up.closed


def test_free_track_options_preflight_includes_cors(tmp_path, mocker):
    mocker.patch.dict(
        os.environ,
        {"FILE_IDS_JSON": json.dumps({"Divine sound Super Feng Shui from God": "dummy_file_id"})},
        clear=False,
    )
    mocker.patch(
        "music_sales.server.resolve_telegram_file_download_url",
        return_value=("https://api.telegram.org/file/botFAKE/music/test.mp3", None),
    )
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://ianaranovitch-swe.github.io")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.options(
        "/free-track",
        headers={"Origin": "https://ianaranovitch-swe.github.io"},
    )
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://ianaranovitch-swe.github.io"


def test_website_download_returns_signed_url(mocker):
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")
    mocker.patch(
        "stripe.checkout.Session.retrieve",
        return_value={
            "payment_status": "paid",
            "metadata": {"source": "website", "song_id": "song1"},
        },
    )

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.get("/website/download?session_id=cs_test_123&track_id=2")

    assert resp.status_code == 200
    body = resp.get_json()
    assert "/website/download-file?" in (body.get("url") or "")


def test_website_download_options_preflight_includes_cors(mocker):
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://ianaranovitch-swe.github.io")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.options(
        "/website/download",
        headers={"Origin": "https://ianaranovitch-swe.github.io"},
    )
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://ianaranovitch-swe.github.io"


def test_website_download_redirect_returns_302_to_file(mocker):
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")
    mocker.patch(
        "stripe.checkout.Session.retrieve",
        return_value={
            "payment_status": "paid",
            "metadata": {"source": "website", "song_id": "song1"},
        },
    )
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.get(
        "/website/download-redirect?session_id=cs_test_redirect&track_id=2",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "website/download-file" in (resp.headers.get("Location") or "")


def test_website_download_file_streams_from_telegram_cdn(mocker, tmp_path):
    """После проверки подписи — прокси-стрим с CDN Telegram (без 302 с BOT_TOKEN в Location)."""
    import hashlib
    import hmac
    import time

    from music_sales import config

    mocker.patch("music_sales.server.file_id_for_song", return_value="dummy_tg_file_id")
    mocker.patch(
        "music_sales.server.resolve_telegram_file_download_url",
        return_value=("https://api.telegram.org/file/botFAKE/music/paid.mp3", None),
    )

    class _FakeUpstream:
        status_code = 200
        headers = {"Content-Length": "6"}
        closed = False

        def iter_content(self, chunk_size=None):
            yield b"fakeMP"

        def close(self):
            self.closed = True

    fake_up = _FakeUpstream()
    mocker.patch("music_sales.server.requests.get", return_value=fake_up)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    song_id = "song1"
    exp = int(time.time()) + 3600
    secret = (config.MINIAPP_CHECKOUT_SECRET or config.BOT_TOKEN or "fallback-secret").encode("utf-8")
    sig = hmac.new(secret, f"{song_id}:{exp}".encode("utf-8"), hashlib.sha256).hexdigest()
    resp = client.get(
        f"/website/download-file?song_id={song_id}&exp={exp}&sig={sig}",
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert resp.data == b"fakeMP"
    assert "audio/mpeg" in (resp.headers.get("Content-Type") or "")
    assert "attachment" in (resp.headers.get("Content-Disposition") or "")
    assert fake_up.closed


def test_website_download_get_json_includes_cors_headers(mocker):
    """GitHub Pages делает fetch к /website/download — в ответе нужен Access-Control-Allow-Origin."""
    mocker.patch("music_sales.config.MINIAPP_CORS_ORIGINS", "https://pages.example")
    mocker.patch("tracks.get_track", return_value={"audio": "songs/song1.mp3"})
    mocker.patch("music_sales.server.resolve_song_id_by_audio_stem", return_value="song1")
    mocker.patch(
        "stripe.checkout.Session.retrieve",
        return_value={
            "payment_status": "paid",
            "metadata": {"source": "website", "song_id": "song1"},
        },
    )
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
    )
    client = app.test_client()
    resp = client.get(
        "/website/download?session_id=cs_test_abc&track_id=2",
        headers={"Origin": "https://pages.example"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://pages.example"


def test_webhook_completed_non_dict_metadata_still_detects_website(mocker, tmp_path):
    """StripeObject metadata: раньше теряли source и вызывали deliver_purchase(0)."""

    class _Meta:
        def to_dict(self):
            return {
                "telegram_id": "0",
                "telegram_name": "Website customer",
                "song_id": "song1",
                "source": "website",
            }

    class _Session:
        def __getitem__(self, key: str):
            if key == "metadata":
                return _Meta()
            if key == "client_reference_id":
                return ""
            raise KeyError(key)

    fake_event = {"type": "checkout.session.completed", "data": {"object": _Session()}}
    mocker.patch("stripe.Event.construct_from", return_value=fake_event)
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
    resp = client.post("/webhook", json={"type": "checkout.session.completed", "id": "evt_test_meta"})

    assert resp.status_code == 200
    urls = [c.args[0] for c in mock_post.call_args_list if c.args]
    assert all("sendDocument" not in u for u in urls)


def test_webhook_completed_telegram_id_zero_skips_telegram_even_without_source(mocker, tmp_path):
    """Запасной путь: даже без source=website не шлём в chat_id=0."""
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "0",
                "metadata": {
                    "telegram_id": "0",
                    "song_id": "song1",
                },
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
    urls = [c.args[0] for c in mock_post.call_args_list if c.args]
    assert all("sendDocument" not in u for u in urls)


def test_webhook_completed_recovers_song_id_from_stripe_line_items(mocker, tmp_path):
    mocker.patch.dict(
        os.environ,
        {"FILE_IDS_JSON": json.dumps({"song1": "telegram_doc_file_id_test"})},
        clear=False,
    )

    # metadata.song_id пустой: воспроизводим реальный инцидент из Railway logs.
    event = {
        "type": "checkout.session.completed",
        "id": "evt_test_123",
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": "555",
                "metadata": {
                    "telegram_id": "555",
                    "song_id": "",
                },
            }
        },
    }
    mocker.patch("stripe.Event.construct_from", return_value=event)
    mocker.patch(
        "stripe.checkout.Session.list_line_items",
        return_value={"data": [{"description": "[TEST] Relaxing Sound"}]},
    )
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
    send_doc_call = mock_post.call_args_list[0]
    assert "sendDocument" in send_doc_call.args[0]
    assert send_doc_call.kwargs["data"]["chat_id"] == 555
    assert send_doc_call.kwargs["data"]["document"] == "telegram_doc_file_id_test"


def test_webhook_completed_recovers_song_id_from_stripeobject_line_items(mocker, tmp_path):
    mocker.patch.dict(
        os.environ,
        {"FILE_IDS_JSON": json.dumps({"song1": "telegram_doc_file_id_test"})},
        clear=False,
    )

    event = {
        "type": "checkout.session.completed",
        "id": "evt_test_456",
        "data": {
            "object": {
                "id": "cs_test_456",
                "client_reference_id": "555",
                "metadata": {"telegram_id": "555", "song_id": ""},
            }
        },
    }

    class _StripeLikeLineItem:
        def __init__(self, description: str):
            self._description = description

        def __getitem__(self, key: str):
            if key == "description":
                return self._description
            raise KeyError(key)

    class _StripeLikeList:
        data = [_StripeLikeLineItem("[TEST] Relaxing Sound")]

    mocker.patch("stripe.Event.construct_from", return_value=event)
    mocker.patch("stripe.checkout.Session.list_line_items", return_value=_StripeLikeList())
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
    send_doc_call = mock_post.call_args_list[0]
    assert "sendDocument" in send_doc_call.args[0]
    assert send_doc_call.kwargs["data"]["chat_id"] == 555
    assert send_doc_call.kwargs["data"]["document"] == "telegram_doc_file_id_test"


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
    send_doc_calls = [
        c for c in mock_post.call_args_list if "sendDocument" in (c.args[0] if c.args else "")
    ]
    assert send_doc_calls == []


def test_deliver_purchase_raises_when_file_id_missing(mocker, tmp_path):
    mocker.patch.dict(os.environ, {"FILE_IDS_JSON": "{}"}, clear=False)
    mock_post = mocker.patch("music_sales.server.requests.post")

    from music_sales.server import deliver_purchase

    with pytest.raises(OSError, match="No Telegram file_id"):
        deliver_purchase(
            telegram_id=555,
            song_id="song1",
            songs_catalog={"song1": {"name": "Relaxing Sound", "file": "songs/song1.mp3"}},
            root=tmp_path,
        )
    mock_post.assert_not_called()


def test_deliver_purchase_posts_send_document(mocker, tmp_path):
    mocker.patch.dict(
        os.environ,
        {"FILE_IDS_JSON": json.dumps({"song1": "fid_abc"})},
        clear=False,
    )
    mock_post = mocker.patch("music_sales.server.requests.post")
    mock_post.return_value.raise_for_status = MagicMock()

    from music_sales.server import deliver_purchase

    deliver_purchase(
        telegram_id=555,
        song_id="song1",
        songs_catalog={"song1": {"name": "Relaxing Sound", "file": "songs/song1.mp3"}},
        root=tmp_path,
    )
    mock_post.assert_called_once()
    assert "sendDocument" in mock_post.call_args[0][0]
    assert mock_post.call_args[1]["data"]["document"] == "fid_abc"


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


def test_website_html_route(mocker, tmp_path):
    (tmp_path / "website.html").write_text("<!doctype html><title>shop</title>", encoding="utf-8")
    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog=_TEST_CATALOG,
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get("/website.html")
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
