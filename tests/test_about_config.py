"""Проверка URL страницы About (HTTPS backend)."""

from music_sales import config


def test_resolved_about_page_url_https_backend(monkeypatch):
    monkeypatch.setenv("BACKEND_URL", "https://api.example.com/")
    assert config.resolved_about_page_url() == "https://api.example.com/about.html"


def test_resolved_about_page_url_prefers_backend_over_domain(monkeypatch):
    monkeypatch.setenv("BACKEND_URL", "https://web-first.example.app")
    monkeypatch.setenv("DOMAIN", "https://other.example.com")
    assert config.resolved_about_page_url() == "https://web-first.example.app/about.html"


def test_resolved_about_page_url_empty_without_https(monkeypatch):
    monkeypatch.setenv("BACKEND_URL", "http://localhost:5000")
    monkeypatch.setenv("DOMAIN", "")
    assert config.resolved_about_page_url() == ""
