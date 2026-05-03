"""
Точка входа бота (polling).

Запуск: ``python -m music_sales.bot_entry`` или ``python run_bot.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import music_sales.env_bootstrap  # noqa: F401

from music_sales.bot_app import main

if __name__ == "__main__":
    main()
