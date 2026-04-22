"""Start the Telegram bot (polling)."""

import music_sales.env_bootstrap  # noqa: F401 — loads .env before config

from music_sales.bot_app import main

if __name__ == "__main__":
    main()
