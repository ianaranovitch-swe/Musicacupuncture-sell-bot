"""TTL подписанных ссылок /website/download-file."""

from music_sales import config


def test_website_download_token_ttl_default_300(monkeypatch):
    monkeypatch.delenv("WEBSITE_DOWNLOAD_TOKEN_TTL_SECONDS", raising=False)
    assert config.website_download_token_ttl_seconds() == 300


def test_website_download_token_ttl_custom(monkeypatch):
    monkeypatch.setenv("WEBSITE_DOWNLOAD_TOKEN_TTL_SECONDS", "600")
    assert config.website_download_token_ttl_seconds() == 600


def test_website_download_token_ttl_capped_at_900(monkeypatch):
    monkeypatch.setenv("WEBSITE_DOWNLOAD_TOKEN_TTL_SECONDS", "7200")
    assert config.website_download_token_ttl_seconds() == 900


def test_website_download_token_ttl_floor_at_60(monkeypatch):
    monkeypatch.setenv("WEBSITE_DOWNLOAD_TOKEN_TTL_SECONDS", "10")
    assert config.website_download_token_ttl_seconds() == 60
