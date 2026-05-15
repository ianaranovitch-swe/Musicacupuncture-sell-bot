"""Тесты pCloud getfilelink (без реального токена)."""

from unittest.mock import MagicMock

from music_sales import pcloud_delivery


def test_resolve_pcloud_direct_download_url_success(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "result": 0,
        "path": "/p/7/test.mp3",
        "hosts": ["c123.pcloud.com"],
    }
    monkeypatch.setattr(pcloud_delivery.requests, "get", MagicMock(return_value=fake_resp))

    from music_sales.pcloud_delivery import resolve_pcloud_direct_download_url

    url, err = resolve_pcloud_direct_download_url("authTOKEN", "12345", api_host="api.pcloud.com")
    assert err is None
    assert url == "https://c123.pcloud.com/p/7/test.mp3"
    pcloud_delivery.requests.get.assert_called_once()
    args, kwargs = pcloud_delivery.requests.get.call_args
    assert "getfilelink" in (args[0] if args else "")
    assert kwargs.get("params", {}).get("auth") == "authTOKEN"
    assert kwargs.get("params", {}).get("fileid") == "12345"


def test_resolve_pcloud_direct_download_url_api_error(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"result": 2002, "error": "invalid fileid"}
    monkeypatch.setattr(pcloud_delivery.requests, "get", MagicMock(return_value=fake_resp))

    from music_sales.pcloud_delivery import resolve_pcloud_direct_download_url

    url, err = resolve_pcloud_direct_download_url("authTOKEN", "bad")
    assert url is None
    assert err is not None
