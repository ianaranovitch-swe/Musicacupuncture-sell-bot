"""
Точка входа бота (polling).

Запуск: ``python -m music_sales.bot_entry``
"""

from __future__ import annotations

import music_sales.env_bootstrap  # noqa: F401

from music_sales.bot_app import main

if __name__ == "__main__":
    main()
