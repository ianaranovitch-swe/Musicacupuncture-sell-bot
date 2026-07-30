"""
Точка входа Flask для Railway / PaaS.

Запуск: ``python -m music_sales.web_entry`` или ``python run_server.py``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Railway / Nixpacks иногда стартуют не из корня репозитория — без этого нет ``import music_sales``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import music_sales.env_bootstrap  # noqa: F401 — loads .env before config

from music_sales.purchase_email import run_smtp_startup_test_if_configured
from music_sales.server import create_app

logger = logging.getLogger(__name__)

app = create_app()


def main() -> None:
    try:
        run_smtp_startup_test_if_configured()
    except Exception:
        # Не блокируем старт веб-сервера из-за SMTP.
        logger.exception("SMTP startup test hook failed (non-fatal)")
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
