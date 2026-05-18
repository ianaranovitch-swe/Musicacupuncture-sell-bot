"""Тесты отзывов (testimonials.py и сопоставление с треками)."""

from music_sales.testimonials_store import (
    find_testimonials_for_track,
    first_sentence,
    format_telegram_review,
    load_visible_testimonials,
    rating_stars,
    save_testimonials,
)


def test_load_visible_testimonials_has_ten():
    items = load_visible_testimonials()
    assert len(items) >= 10


def test_three_reviews_have_four_stars():
    items = load_visible_testimonials()
    four_star = [t for t in items if int(t.get("rating") or 0) == 4]
    assert len(four_star) == 3


def test_find_testimonials_for_track_heart():
    found = find_testimonials_for_track("Divine sound Heart from God")
    assert len(found) == 1
    assert found[0]["name"] == "Sarah M."


def test_find_testimonials_crownchakra_fuzzy_hyphens():
    found = find_testimonials_for_track("Divine sound Crownchakra-Browchakra-Throatchakra from God")
    assert len(found) == 1
    assert found[0]["id"] == 4


def test_format_telegram_review_includes_counter():
    item = load_visible_testimonials()[0]
    text = format_telegram_review(item, index=2, total=10)
    assert "Review 2 of 10" in text
    assert rating_stars(5) in text


def test_first_sentence_truncates_long_text():
    long = "A" * 200 + ". Still more text here."
    s = first_sentence(long, max_len=50)
    assert len(s) <= 50


def test_save_testimonials_writes_json_and_env(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "music_sales.testimonials_store._testimonials_path",
        lambda: tmp_path / "testimonials.py",
    )
    monkeypatch.setattr(
        "music_sales.testimonials_store._testimonials_json_path",
        lambda: tmp_path / "testimonials.json",
    )
    save_testimonials(
        [
            {
                "id": 1,
                "name": "X",
                "city": "Y",
                "track": "T",
                "rating": 5,
                "visible": False,
                "text": "Updated",
            }
        ]
    )
    text = (tmp_path / "testimonials.py").read_text(encoding="utf-8")
    assert '"visible": False' in text
    assert "Updated" in text
    import json
    import os

    assert json.loads((tmp_path / "testimonials.json").read_text(encoding="utf-8"))[0]["text"] == "Updated"
    assert "Updated" in os.environ.get("TESTIMONIALS_JSON", "")
