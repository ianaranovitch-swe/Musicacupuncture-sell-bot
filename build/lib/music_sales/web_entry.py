"""
Точка входа Flask для Railway / PaaS.

Запуск: ``python -m music_sales.web_entry``

Так сервер стартует из пакета ``music_sales/``, даже если в контейнере нет
``run_server.py`` в корне (частая причина: Root Directory или сборка).
"""

from __future__ import annotations

import os

import music_sales.env_bootstrap  # noqa: F401 — loads .env before config

from music_sales.server import create_app

app = create_app()


def main() -> None:
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
