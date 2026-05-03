"""Обёртка: локально ``python run_bot.py``."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from music_sales.bot_entry import main

if __name__ == "__main__":
    main()
