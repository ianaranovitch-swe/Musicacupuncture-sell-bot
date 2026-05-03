"""
Точка входа Flask для Railway / PaaS.

Запуск: ``python -m music_sales.web_entry`` или ``python run_server.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Railway / Nixpacks иногда стартуют не из корня репозитория — без этого нет ``import music_sales``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import music_sales.env_bootstrap  # noqa: F401 — loads .env before config

from music_sales.server import create_app

app = create_app()


def main() -> None:
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
