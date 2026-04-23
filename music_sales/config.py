import os


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


BOT_TOKEN = _env("BOT_TOKEN")
BACKEND_URL = _env("BACKEND_URL", "http://localhost:5000")
STRIPE_SECRET_KEY = _env("STRIPE_SECRET_KEY")
# Секрет подписи вебхука Stripe (Stripe Dashboard → Webhooks → Signing secret). В проде обязателен.
STRIPE_WEBHOOK_SECRET = _env("STRIPE_WEBHOOK_SECRET")
DOMAIN = _env("DOMAIN", "http://localhost:5000")

# Telegram Payments (Stripe): provider token из BotFather (нужен для sendInvoice)
PAYMENTS_PROVIDER_TOKEN = _env("PAYMENTS_PROVIDER_TOKEN")
# Валюта инвойса Telegram Payments (должна совпадать с валютой Stripe Checkout)
PAYMENTS_CURRENCY = _env("PAYMENTS_CURRENCY", "USD")
# Владелец бота: получает личное сообщение, когда кто-то нажал /start (можно переопределить OWNER_TELEGRAM_ID)
OWNER_TELEGRAM_ID = _env("OWNER_TELEGRAM_ID", "7846059164")
# Цена по умолчанию (USD, целые доллары) для файлов в SONGS/, если не задано иначе в коде/окружении
DEFAULT_TRACK_PRICE_USD = _env("DEFAULT_TRACK_PRICE_USD", "16")
# Обратная совместимость (старое имя переменной): используется только если DEFAULT_TRACK_PRICE_USD пустой
DEFAULT_TRACK_PRICE_SEK = _env("DEFAULT_TRACK_PRICE_SEK", "")


def owner_telegram_id_int() -> int | None:
    if not OWNER_TELEGRAM_ID:
        return None
    try:
        return int(OWNER_TELEGRAM_ID)
    except ValueError:
        return None


# Логирование (бот): LOG_LEVEL=DEBUG|INFO|WARNING|ERROR; LOG_FILE по умолчанию logs/bot.log
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
LOG_FILE_RAW = os.environ.get("LOG_FILE")
if LOG_FILE_RAW is None:
    LOG_FILE = "logs/bot.log"
else:
    LOG_FILE = LOG_FILE_RAW.strip()
    if LOG_FILE.lower() in ("none", "false", "-"):
        LOG_FILE = ""
