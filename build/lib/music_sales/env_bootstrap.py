"""Загрузить `.env` из корня проекта до того, как другие модули читают os.environ."""

from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
