"""
Создание Stripe Product + Price + Payment Link (USD и SEK) для нового трека.
"""

from __future__ import annotations

import json
import logging

import stripe

from music_sales import config

logger = logging.getLogger(__name__)


def create_product_and_payment_links(
    *,
    title: str,
    usd_whole: int,
    sek_whole: int,
) -> dict[str, str]:
    """
    Возвращает словарь: product_id, price_usd_id, price_sek_id, buy_url_usd, buy_url_sek.

    При ошибке Stripe — бросает stripe.error.StripeError.
    """
    key = (config.STRIPE_SECRET_KEY or "").strip()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    stripe.api_key = key
    test = config.test_mode_active()
    display = f"[TEST] {title}" if test else title

    product = stripe.Product.create(name=display[:120])
    pid = str(product["id"] if isinstance(product, dict) else product.id)

    usd_cents = max(50, int(usd_whole) * 100)
    sek_ore = max(100, int(sek_whole) * 100)

    price_usd = stripe.Price.create(
        product=pid,
        unit_amount=usd_cents,
        currency="usd",
    )
    price_sek = stripe.Price.create(
        product=pid,
        unit_amount=sek_ore,
        currency="sek",
    )
    puid = str(price_usd["id"] if isinstance(price_usd, dict) else price_usd.id)
    psek = str(price_sek["id"] if isinstance(price_sek, dict) else price_sek.id)

    link_usd = stripe.PaymentLink.create(line_items=[{"price": puid, "quantity": 1}])
    link_sek = stripe.PaymentLink.create(line_items=[{"price": psek, "quantity": 1}])
    url_usd = str(link_usd["url"] if isinstance(link_usd, dict) else link_usd.url)
    url_sek = str(link_sek["url"] if isinstance(link_sek, dict) else link_sek.url)

    return {
        "stripe_product_id": pid,
        "stripe_price_usd_id": puid,
        "stripe_price_sek_id": psek,
        "buy_url": url_usd,
        "buy_url_sek": url_sek,
    }


def merge_file_id_json(stem: str, file_id: str) -> None:
    """Дописать stem → file_id в корневой file_ids.json."""
    from music_sales.file_id_delivery import _file_ids_json_path, load_file_ids_from_disk

    data = dict(load_file_ids_from_disk())
    data[str(stem).strip()] = str(file_id).strip()
    p = _file_ids_json_path()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
