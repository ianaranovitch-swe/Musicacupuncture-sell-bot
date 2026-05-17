#!/usr/bin/env python3
"""
Перезаписать блоки MA_AUTO_* в miniapp.html и website.html из tracks.TRACKS.

Зачем: на GitHub Pages лежит статический HTML — в нём зашиты buyUrl / buyUrlSek.
TEST_MODE на Railway (Web + Worker) переключает тест/live без пересборки HTML:
  TEST_MODE=true  — дешёвые цены, /miniapp-pricing, /website-create-payment, бот.
  TEST_MODE=false — боевые цены и Stripe Checkout.

Скрипт sync пишет в HTML боевые buyUrl из tracks.py (fallback, если API недоступен).
Запускайте sync с TEST_MODE=false (или без TEST_MODE в .env), чтобы в git не попали тест-ссылки.

Как пользоваться (локально, перед push статики на GitHub Pages):
  1) TEST_MODE=false в .env (или не задавать TEST_MODE)
  2) python scripts/sync_frontend_from_env.py
  3) git add miniapp.html website.html …

Railway: TEST_MODE и TEST_PAYMENT_LINK только в Variables — redeploy Web + Worker.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import tracks

tracks.reload_track_catalog()

from music_sales.frontend_catalog_sync import sync_frontend_html_catalog


def main() -> int:
    res = sync_frontend_html_catalog(root=ROOT)
    for p in res.written:
        print("updated:", p)
    for err in res.errors:
        print("error:", err)
    return 1 if res.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
