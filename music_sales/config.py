import os


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


BOT_TOKEN = _env("BOT_TOKEN")
BACKEND_URL = _env("BACKEND_URL", "http://localhost:5000")
STRIPE_SECRET_KEY = _env("STRIPE_SECRET_KEY")
# From Stripe Dashboard → Webhooks → Signing secret (required in production)
STRIPE_WEBHOOK_SECRET = _env("STRIPE_WEBHOOK_SECRET")
DOMAIN = _env("DOMAIN", "http://localhost:5000")
# Bot owner: receives a DM when someone uses /start. Override with OWNER_TELEGRAM_ID.
OWNER_TELEGRAM_ID = _env("OWNER_TELEGRAM_ID", "7846059164")
# Default price (SEK) for files in SONGS/ when not set in SONGS/catalog.json
DEFAULT_TRACK_PRICE_SEK = _env("DEFAULT_TRACK_PRICE_SEK", "50")


def owner_telegram_id_int() -> int | None:
    if not OWNER_TELEGRAM_ID:
        return None
    try:
        return int(OWNER_TELEGRAM_ID)
    except ValueError:
        return None


# Logging (bot): LOG_LEVEL=DEBUG|INFO|WARNING|ERROR; LOG_FILE default logs/bot.log
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
LOG_FILE_RAW = os.environ.get("LOG_FILE")
if LOG_FILE_RAW is None:
    LOG_FILE = "logs/bot.log"
else:
    LOG_FILE = LOG_FILE_RAW.strip()
    if LOG_FILE.lower() in ("none", "false", "-"):
        LOG_FILE = ""
