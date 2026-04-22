"""Start the Flask + Stripe backend."""

import music_sales.env_bootstrap  # noqa: F401 — loads .env before config

from music_sales.server import create_app

app = create_app()

if __name__ == "__main__":
    app.run(port=5000)
