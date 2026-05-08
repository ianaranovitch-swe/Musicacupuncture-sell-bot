"""Тесты генерации фронтового каталога из словарей треков."""

from __future__ import annotations

from pathlib import Path

from music_sales.frontend_catalog_sync import (
    miniapp_js_block,
    ordered_frontend_pairs,
    peel_emoji_short,
    sync_frontend_html_catalog,
    website_js_block,
)


def test_peel_emoji_short_splits_emoji_prefix() -> None:
    assert peel_emoji_short("🎵 Estrogen") == ("🎵", "Estrogen")
    assert peel_emoji_short("🎁 Free Gift") == ("🎁", "Free Gift")


def test_peel_emoji_short_latin_first_word() -> None:
    emoji, name = peel_emoji_short("Vitamin track")
    assert emoji == "🎵"
    assert name == "Vitamin track"


def test_ordered_frontend_free_then_paid_by_id() -> None:
    tracks = [
        {"id": 3, "price": "$16", "short_title": "🎵 Three", "title": "T3", "description": "d", "cover": "c3.png"},
        {"id": 17, "price": "FREE", "short_title": "🎁 G", "title": "Free", "description": "f", "cover": "cf.png"},
        {"id": 1, "price": "$16", "short_title": "🎵 One", "title": "T1", "description": "d", "cover": "c1.png"},
    ]
    pairs = ordered_frontend_pairs(tracks)
    assert [p[0] for p in pairs] == [0, 1, 3]
    assert pairs[0][1]["id"] == 17


def test_miniapp_js_contains_real_ids_for_paid() -> None:
    tracks = [
        {"id": 99, "price": "FREE", "short_title": "🎁 X", "title": "Free T", "description": "a\nb", "cover": "c/f.png"},
        {"id": 5, "price": "$16", "short_title": "🎵 P", "title": "Paid", "description": "d", "cover": "x.png"},
    ]
    js = miniapp_js_block(tracks)
    assert '"id": 0' in js
    assert '"id": 5' in js
    assert "Free T" in js


def test_website_js_stripe_fields_for_paid() -> None:
    tracks = [
        {"id": 2, "price": "FREE", "short_title": "🎁 F", "title": "F", "description": "d", "cover": "c.png"},
        {
            "id": 10,
            "price": "$16",
            "short_title": "🎵 Ten",
            "title": "Ten",
            "description": "d",
            "cover": "t.png",
            "buy_url": "https://buy.stripe.com/usd",
            "buy_url_sek": "https://buy.stripe.com/sek",
        },
    ]
    js = website_js_block(tracks)
    assert '"buyUrlUsd": "https://buy.stripe.com/usd"' in js
    assert '"buyUrlSek": "https://buy.stripe.com/sek"' in js
    assert '"buyUrlUsd": null' in js  # free entry


def test_sync_updates_marked_miniapp(tmp_path: Path) -> None:
    p = tmp_path / "miniapp.html"
    p.write_text(
        "head\n"
        "    /* MA_AUTO_TRACKS_BEGIN */\n"
        "    const tracks = [\n"
        "      OLD\n"
        "    ];\n"
        "    /* MA_AUTO_TRACKS_END */\n"
        "tail\n",
        encoding="utf-8",
    )
    fake_tracks = [
        {
            "id": 1,
            "price": "FREE",
            "short_title": "🎁 F",
            "title": "Freebie",
            "description": "d",
            "cover": "covers/x.png",
            "audio": "songs/x.mp3",
        },
        {
            "id": 2,
            "price": "$16",
            "short_title": "🎵 Two",
            "title": "Paid Two",
            "description": "pd",
            "cover": "covers/y.png",
            "audio": "songs/y.mp3",
            "buy_url": "https://example.com/u",
            "buy_url_sek": "https://example.com/s",
        },
    ]
    res = sync_frontend_html_catalog(root=tmp_path, tracks=fake_tracks)
    assert not res.errors
    body = p.read_text(encoding="utf-8")
    assert "Freebie" in body
    assert "OLD" not in body
