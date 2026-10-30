"""
SEO: публичный URL, sitemap, robots, JSON-LD, сниппеты аналитики.

Не трогает Stripe/checkout — только публичные HTML-маршруты и метаданные.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from music_sales import config

logger = logging.getLogger(__name__)

SITE_ORIGIN_DEFAULT = "https://musicacupuncture.digital"
OG_IMAGE_PATH = "/assets/og-musicacupuncture.png"

# Публичные страницы для sitemap (path → приоритет, changefreq)
PUBLIC_PAGES: list[tuple[str, str, str]] = [
    ("/", "1.0", "weekly"),
    ("/about.html", "0.8", "monthly"),
    ("/blog/", "0.8", "weekly"),
    ("/blog/what-is-music-acupuncture.html", "0.7", "monthly"),
    ("/blog/acupuncture-meridians-and-sound.html", "0.7", "monthly"),
    ("/blog/music-therapy-for-relaxation.html", "0.7", "monthly"),
]

ROBOTS_DISALLOW = (
    "/webhook",
    "/create-checkout",
    "/create-payment",
    "/website-create-payment",
    "/website/download",
    "/website/download-redirect",
    "/website/download-file",
    "/internal/",
    "/health",
    "/success",
    "/cancel",
    "/miniapp-pricing",
)


def public_site_origin() -> str:
    """Канонический origin без trailing slash (предпочитаем DOMAIN / BACKEND_URL)."""
    for raw in (
        (os.environ.get("PUBLIC_SITE_URL") or "").strip(),
        (config.DOMAIN or "").strip(),
        (config.BACKEND_URL or "").strip(),
    ):
        if not raw:
            continue
        if not raw.startswith("http"):
            raw = f"https://{raw}"
        origin = raw.rstrip("/")
        # Локальный хост не публикуем в sitemap/canonical
        low = origin.lower()
        if "localhost" in low or "127.0.0.1" in low:
            continue
        return origin
    return SITE_ORIGIN_DEFAULT


def absolute_url(path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    return f"{public_site_origin()}{p}"


def og_image_url() -> str:
    return absolute_url(OG_IMAGE_PATH)


def google_site_verification() -> str:
    return (os.environ.get("GOOGLE_SITE_VERIFICATION") or "").strip()


def ga4_measurement_id() -> str:
    return (os.environ.get("GA4_MEASUREMENT_ID") or "").strip()


def analytics_head_html() -> str:
    """
    Meta verification + GA4 (только если заданы env).
    Пустые ID → пустая строка (без фейковых сниппетов).
    """
    parts: list[str] = []
    ver = google_site_verification()
    if ver:
        parts.append(
            f'<meta name="google-site-verification" content="{_html_attr(ver)}" />'
        )
    ga = ga4_measurement_id()
    if ga and ga.startswith("G-"):
        parts.append(
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={_html_attr(ga)}"></script>'
        )
        parts.append(
            "<script>"
            "window.dataLayer=window.dataLayer||[];"
            "function gtag(){dataLayer.push(arguments);}"
            "gtag('js',new Date());"
            f"gtag('config','{_html_attr(ga)}');"
            "</script>"
        )
    return "\n".join(parts)


def _html_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def robots_txt() -> str:
    lines = [
        "User-agent: *",
        "Allow: /",
    ]
    for path in ROBOTS_DISALLOW:
        lines.append(f"Disallow: {path}")
    lines.append("")
    lines.append(f"Sitemap: {absolute_url('/sitemap.xml')}")
    lines.append("")
    return "\n".join(lines)


def sitemap_xml(*, lastmod: str | None = None) -> str:
    """Автогенерация sitemap: все публичные страницы + hreflang en + x-default."""
    if not lastmod:
        lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    origin = public_site_origin()
    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for path, priority, changefreq in PUBLIC_PAGES:
        loc = f"{origin}{path}"
        chunks.append("  <url>")
        chunks.append(f"    <loc>{xml_escape(loc)}</loc>")
        chunks.append(f"    <lastmod>{xml_escape(lastmod)}</lastmod>")
        chunks.append(f"    <changefreq>{changefreq}</changefreq>")
        chunks.append(f"    <priority>{priority}</priority>")
        # Сейчас только EN; x-default = EN (SV добавим позже)
        chunks.append(
            f'    <xhtml:link rel="alternate" hreflang="en" href="{xml_escape(loc)}" />'
        )
        chunks.append(
            f'    <xhtml:link rel="alternate" hreflang="x-default" href="{xml_escape(loc)}" />'
        )
        chunks.append("  </url>")
    chunks.append("</urlset>")
    chunks.append("")
    return "\n".join(chunks)


def _tracks_for_product_schema() -> list[dict[str, Any]]:
    try:
        from tracks import TRACKS

        return [dict(t) for t in TRACKS if isinstance(t, dict)]
    except Exception:
        logger.debug("seo: TRACKS unavailable", exc_info=True)
        return []


def build_home_json_ld() -> list[dict[str, Any]]:
    """Organization + WebSite + FAQPage + BreadcrumbList + ItemList(Product)."""
    origin = public_site_origin()
    org = {
        "@type": "Organization",
        "@id": f"{origin}/#organization",
        "name": "Musicacupuncture",
        "alternateName": ["Music Acupuncture", "MusicAcupuncture®"],
        "url": f"{origin}/",
        "logo": og_image_url(),
        "image": og_image_url(),
        "description": (
            "Therapeutic music for acupuncture meridians — healing music MP3 "
            "for relaxation, meditation, and energy balance by Michael B. Johnsson."
        ),
        "founder": {
            "@type": "Person",
            "name": "Michael B. Johnsson",
            "url": f"{origin}/about.html",
        },
        "sameAs": [
            "https://www.facebook.com/profile.php?id=61567173356607",
            "https://www.youtube.com/@MichaelJohnsson-r4o",
        ],
    }
    website = {
        "@type": "WebSite",
        "@id": f"{origin}/#website",
        "url": f"{origin}/",
        "name": "Musicacupuncture",
        "description": (
            "Buy healing music MP3 and music therapy for acupuncture meridians, "
            "sound healing, and relaxation."
        ),
        "publisher": {"@id": f"{origin}/#organization"},
        "inLanguage": "en",
    }
    faq = {
        "@type": "FAQPage",
        "@id": f"{origin}/#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What is Music Acupuncture?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Music Acupuncture (Musicacupuncture) is a therapeutic music approach "
                        "that uses carefully crafted sound frequencies inspired by acupuncture "
                        "meridians and energetic principles. It is designed to support relaxation, "
                        "meditation, and a sense of energy balance — not to diagnose or treat medical conditions."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "How is music connected to acupuncture meridians?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Tracks are composed with intention around meridians, chakras, and elemental "
                        "balance. Listeners use them as a gentle daily sound practice for calm and well-being."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "How should I listen to healing music MP3s?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Use headphones or speakers at a comfortable volume. Many people listen during "
                        "meditation, rest, or quiet evening routines. Start with 10–20 minutes and adjust "
                        "to what feels good for you."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "Who is Music Acupuncture for?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Anyone seeking music for relaxation and stress relief, meditation music, "
                        "or sound healing as a wellness companion. It complements — and does not replace — "
                        "professional medical care."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "How do I buy healing music MP3?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Browse the Music Catalog on musicacupuncture.digital, choose a track, "
                        "and pay securely with Stripe (card or Klarna where available). After payment "
                        "you can download the MP3 immediately."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "Is there a free track?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Yes. Divine sound Super Feng Shui from God is available as a free download "
                        "so you can experience Music Acupuncture before purchasing."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "Does this music cure diseases?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "No. Musicacupuncture supports relaxation and well-being. It is not medical "
                        "treatment and does not replace advice from a licensed healthcare professional."
                    ),
                },
            },
        ],
    }
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": f"{origin}/",
            }
        ],
    }

    products: list[dict[str, Any]] = []
    for t in _tracks_for_product_schema():
        tid = t.get("id")
        title = str(t.get("title") or t.get("name") or "").strip()
        if not title:
            continue
        try:
            tid_int = int(tid)
        except (TypeError, ValueError):
            tid_int = -1
        # Бесплатный gift (id 18 в tracks / 0 на сайте) — Offer price 0
        price_label = str(t.get("price") or "").strip().upper()
        is_free = (
            bool(t.get("is_free"))
            or tid_int in (0, 18)
            or price_label in ("FREE", "0", "$0")
            or int(t.get("price_amount") or -1) == 0
        )
        try:
            if t.get("usd_price") is not None:
                price_usd = float(t.get("usd_price"))
            elif t.get("price_usd") is not None:
                price_usd = float(t.get("price_usd"))
            elif t.get("price_amount") is not None:
                price_usd = float(t.get("price_amount"))
            else:
                price_usd = 0.0
        except (TypeError, ValueError):
            price_usd = 0.0
        if is_free:
            price_usd = 0.0
        cover = str(t.get("cover") or "").strip().lstrip("/")
        image = absolute_url(f"/{cover}") if cover else og_image_url()
        product: dict[str, Any] = {
            "@type": "Product",
            "name": title,
            "description": str(t.get("description") or title)[:500],
            "image": image,
            "brand": {"@type": "Brand", "name": "Musicacupuncture"},
            "category": "MusicRecording",
            "offers": {
                "@type": "Offer",
                "url": f"{origin}/#shop",
                "priceCurrency": "USD",
                "price": f"{price_usd:.2f}",
                "availability": "https://schema.org/InStock",
                "itemCondition": "https://schema.org/NewCondition",
            },
        }
        # MusicRecording — дополнительный тип через @type list
        product["@type"] = ["Product", "MusicRecording"]
        product["byArtist"] = {
            "@type": "Person",
            "name": "Michael B. Johnsson",
        }
        products.append(product)

    item_list: dict[str, Any] | None = None
    if products:
        item_list = {
            "@type": "ItemList",
            "name": "Musicacupuncture healing music catalog",
            "numberOfItems": len(products),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "item": p,
                }
                for i, p in enumerate(products)
            ],
        }

    graph: list[dict[str, Any]] = [org, website, faq, breadcrumb]
    if item_list:
        graph.append(item_list)
    return [
        {
            "@context": "https://schema.org",
            "@graph": graph,
        }
    ]


def json_ld_script_tag(payload: list[dict[str, Any]] | dict[str, Any]) -> str:
    """Безопасный <script type=application/ld+json> (экранируем </script>)."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e")
    return f'<script type="application/ld+json">{raw}</script>'


def inject_seo_into_html(html: str, *, page: str = "home") -> str:
    """
    Подставляет analytics + JSON-LD в маркеры HTML.
    Маркеры: <!-- SEO_ANALYTICS --> и <!-- SEO_JSONLD -->
    """
    out = html
    analytics = analytics_head_html()
    if "<!-- SEO_ANALYTICS -->" in out:
        out = out.replace("<!-- SEO_ANALYTICS -->", analytics)
    if page == "home" and "<!-- SEO_JSONLD -->" in out:
        try:
            ld = build_home_json_ld()
            out = out.replace("<!-- SEO_JSONLD -->", json_ld_script_tag(ld))
        except Exception:
            logger.exception("seo: failed to build home JSON-LD")
            out = out.replace("<!-- SEO_JSONLD -->", "")
    elif "<!-- SEO_JSONLD -->" in out:
        out = out.replace("<!-- SEO_JSONLD -->", "")
    return out
