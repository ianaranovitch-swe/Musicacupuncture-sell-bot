"""Start the Flask + Stripe backend."""

import os

import music_sales.env_bootstrap  # noqa: F401 — loads .env before config

from music_sales.server import create_app

app = create_app()

if __name__ == "__main__":
    # Для Railway и других PaaS порт приходит через переменную окружения PORT.
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
