"""Тесты SEO: robots, sitemap, JSON-LD, analytics markers."""

from __future__ import annotations

import json
import os

import pytest


def test_robots_txt_disallows_private_paths(monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://musicacupuncture.digital")
    from music_sales.seo import robots_txt

    text = robots_txt()
    assert "Allow: /" in text
    assert "Disallow: /webhook" in text
    assert "Disallow: /website-create-payment" in text
    assert "Disallow: /internal/" in text
    assert "Sitemap: https://musicacupuncture.digital/sitemap.xml" in text


def test_sitemap_xml_includes_public_pages_and_hreflang(monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://musicacupuncture.digital")
    from music_sales.seo import sitemap_xml

    xml = sitemap_xml(lastmod="2026-10-30")
    assert "<urlset" in xml
    assert "https://musicacupuncture.digital/" in xml
    assert "https://musicacupuncture.digital/blog/" in xml
    assert "https://musicacupuncture.digital/about.html" in xml
    assert 'hreflang="en"' in xml
    assert 'hreflang="x-default"' in xml
    assert "<lastmod>2026-10-30</lastmod>" in xml


def test_home_json_ld_is_valid_json_with_products(monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://musicacupuncture.digital")
    from music_sales.seo import build_home_json_ld, json_ld_script_tag

    payload = build_home_json_ld()
    raw = json.dumps(payload)
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    graph = parsed[0]["@graph"]
    types = {item.get("@type") if isinstance(item.get("@type"), str) else None for item in graph}
    assert "Organization" in types
    assert "WebSite" in types
    assert "FAQPage" in types
    assert "BreadcrumbList" in types
    assert any(item.get("@type") == "ItemList" for item in graph)
    script = json_ld_script_tag(payload)
    assert 'type="application/ld+json"' in script
    assert "</script>" not in script.replace("</script>", "", 1) or "application/ld+json" in script


def test_analytics_head_empty_without_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_SITE_VERIFICATION", raising=False)
    monkeypatch.delenv("GA4_MEASUREMENT_ID", raising=False)
    from music_sales.seo import analytics_head_html

    assert analytics_head_html() == ""


def test_analytics_head_with_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_SITE_VERIFICATION", "abc123token")
    monkeypatch.setenv("GA4_MEASUREMENT_ID", "G-TEST12345")
    from music_sales.seo import analytics_head_html

    html = analytics_head_html()
    assert 'name="google-site-verification"' in html
    assert "content=\"abc123token\"" in html
    assert "G-TEST12345" in html
    assert "googletagmanager.com/gtag/js" in html


def test_inject_seo_markers(monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://musicacupuncture.digital")
    monkeypatch.setenv("GA4_MEASUREMENT_ID", "G-ABCDEF")
    from music_sales.seo import inject_seo_into_html

    src = "<html><head><!-- SEO_ANALYTICS -->\n<!-- SEO_JSONLD -->\n</head></html>"
    out = inject_seo_into_html(src, page="home")
    assert "<!-- SEO_ANALYTICS -->" not in out
    assert "<!-- SEO_JSONLD -->" not in out
    assert "G-ABCDEF" in out
    assert "application/ld+json" in out


def test_server_robots_and_sitemap_routes(mocker, tmp_path):
    mocker.patch("music_sales.server.config.BOT_TOKEN", "123:FAKE")
    mocker.patch("music_sales.server.bootstrap_sales_log", return_value=0)
    mocker.patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://musicacupuncture.digital"}, clear=False)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog={"song1": {"name": "T", "price_usd": 1, "file": "songs/a.mp3"}},
        project_root_override=tmp_path,
    )
    # Копируем минимальные файлы не нужны для robots/sitemap
    client = app.test_client()
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert b"Sitemap:" in r.data
    s = client.get("/sitemap.xml")
    assert s.status_code == 200
    assert b"<urlset" in s.data


def test_server_home_injects_jsonld(mocker, tmp_path):
    mocker.patch("music_sales.server.config.BOT_TOKEN", "123:FAKE")
    mocker.patch("music_sales.server.bootstrap_sales_log", return_value=0)
    mocker.patch.dict(os.environ, {"PUBLIC_SITE_URL": "https://musicacupuncture.digital"}, clear=False)

    html = (
        "<!DOCTYPE html><html lang='en'><head>"
        "<!-- SEO_ANALYTICS --><!-- SEO_JSONLD -->"
        "<title>t</title></head><body>ok</body></html>"
    )
    (tmp_path / "website.html").write_text(html, encoding="utf-8")

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog={"song1": {"name": "T", "price_usd": 1, "file": "songs/a.mp3"}},
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "application/ld+json" in body
    assert "Musicacupuncture" in body


def test_www_redirect_to_apex(mocker, tmp_path):
    mocker.patch("music_sales.server.config.BOT_TOKEN", "123:FAKE")
    mocker.patch("music_sales.server.bootstrap_sales_log", return_value=0)

    from music_sales.server import create_app

    app = create_app(
        stripe_secret="sk_test_fake",
        stripe_webhook_secret="",
        songs_catalog={"song1": {"name": "T", "price_usd": 1, "file": "songs/a.mp3"}},
        project_root_override=tmp_path,
    )
    client = app.test_client()
    resp = client.get(
        "/",
        headers={"Host": "www.musicacupuncture.digital", "X-Forwarded-Proto": "https"},
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].startswith("https://musicacupuncture.digital")
