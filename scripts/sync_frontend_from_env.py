#!/usr/bin/env python3
"""
Перезаписать блоки MA_AUTO_* в miniapp.html и website.html из tracks.TRACKS.

Зачем: на GitHub Pages лежит статический HTML — в нём зашиты buyUrl / buyUrlSek.
При TEST_MODE=true и TEST_PAYMENT_LINK в .env нужно пересобрать этот блок локально и закоммитить.

Как пользоваться (локально, перед push на GitHub Pages):
  1) В .env выставьте TEST_MODE=true и TEST_PAYMENT_LINK=https://buy.stripe.com/test_...
  2) Из корня репозитория:  python scripts/sync_frontend_from_env.py
  3) Проверьте diff в miniapp.html, website.html (и _site/*.html если есть)
  4) git add / commit / push

Railway: сервису этот скрипт не обязателен — оплата идёт через /website-create-payment и .env там.
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
