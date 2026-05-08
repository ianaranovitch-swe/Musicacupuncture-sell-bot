import os
from urllib.parse import quote


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def test_mode_active() -> bool:
    """
    Режим тестовых цен и ссылок (читаем os.environ при каждом вызове — как CORS, чтобы тесты и Railway подхватывали без перезагрузки модуля).

    В .env: TEST_MODE=true | 1 | yes | on
    """
    v = (os.environ.get("TEST_MODE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


BOT_TOKEN = _env("BOT_TOKEN")
BACKEND_URL = _env("BACKEND_URL", "http://localhost:5000")
STRIPE_SECRET_KEY = _env("STRIPE_SECRET_KEY")
# Секрет подписи вебхука Stripe (Stripe Dashboard → Webhooks → Signing secret). В проде обязателен.
STRIPE_WEBHOOK_SECRET = _env("STRIPE_WEBHOOK_SECRET")
DOMAIN = _env("DOMAIN", "http://localhost:5000")
# Полный HTTPS URL Mini App (например https://your-service.up.railway.app/miniapp.html).
# Если пусто, при HTTPS в DOMAIN подставляется {DOMAIN}/miniapp.html
MINIAPP_URL = _env("MINIAPP_URL")
# Разрешённые Origin для CORS к POST /create-checkout (Mini App на GitHub Pages), через запятую.
# Пример: https://dittnamn.github.io
MINIAPP_CORS_ORIGINS = _env("MINIAPP_CORS_ORIGINS")
# Опционально: общий секрет; Mini App шлёт заголовок X-Miniapp-Checkout-Secret (тот же текст в .env).
MINIAPP_CHECKOUT_SECRET = _env("MINIAPP_CHECKOUT_SECRET")
# Stripe Checkout: сумма в öre для валюты sek (169 kr = 16900).
CHECKOUT_SEK_UNIT_AMOUNT = _env("CHECKOUT_SEK_UNIT_AMOUNT", "16900")
# Куда редиректить после успешной оплаты Stripe (обычно deep-link в Telegram бота).
# Пример: https://t.me/musicacupuncture_bot
CHECKOUT_SUCCESS_URL = _env("CHECKOUT_SUCCESS_URL")

# Telegram Payments (Stripe): provider token из BotFather (нужен для sendInvoice)
PAYMENTS_PROVIDER_TOKEN = _env("PAYMENTS_PROVIDER_TOKEN")
# Валюта инвойса Telegram Payments (должна совпадать с валютой Stripe Checkout)
PAYMENTS_CURRENCY = _env("PAYMENTS_CURRENCY", "USD")
# Владелец бота: получает личные события о запуске, кликах и статусах оплаты.
OWNER_TELEGRAM_ID = _env("OWNER_TELEGRAM_ID", "7973899604")
# Разработчик: тот же доступ к /health, что и у владельца (можно переопределить в .env).
DEVELOPER_TELEGRAM_ID = _env("DEVELOPER_TELEGRAM_ID", "7973899604")
# Папка в корне проекта с аудио для витрины (по умолчанию `songs`; для старых установок можно задать `SONGS`)
AUDIO_SALES_DIR = _env("AUDIO_SALES_DIR", "songs")
# Цена по умолчанию (USD, целые доллары) для файлов в этой папке, если не задано иначе в коде/окружении
DEFAULT_TRACK_PRICE_USD = _env("DEFAULT_TRACK_PRICE_USD", "16")
# Обратная совместимость (старое имя переменной): используется только если DEFAULT_TRACK_PRICE_USD пустой
DEFAULT_TRACK_PRICE_SEK = _env("DEFAULT_TRACK_PRICE_SEK", "")
# TEST_MODE: см. test_mode_active(). Цены теста (целые доллары / целые SEK).
TEST_PRICE_USD = _env("TEST_PRICE_USD", "1")
TEST_PRICE_SEK = _env("TEST_PRICE_SEK", "10")
# Опционально: готовые Stripe Payment Links для простого бота (bot.py), не для динамического Checkout с webhook.
TEST_PAYMENT_LINK_USD = _env("TEST_PAYMENT_LINK_USD")
TEST_PAYMENT_LINK_SEK = _env("TEST_PAYMENT_LINK_SEK")


def resolved_miniapp_url() -> str:
    """
    URL для кнопки WebApp в Telegram.

    Telegram Mini App в проде требует https://.
    Если задан HTTPS BACKEND_URL — добавляем checkout_api=... чтобы Mini App мог вызвать create-checkout.
    """
    direct = (MINIAPP_URL or "").strip()
    if direct.startswith("https://"):
        base = direct
    else:
        base_dom = (DOMAIN or "").strip().rstrip("/")
        if base_dom.startswith("https://"):
            base = f"{base_dom}/miniapp.html"
        else:
            return ""
    api = (BACKEND_URL or "").strip().rstrip("/")
    if api.startswith("https://"):
        sep = "&" if "?" in base else "?"
        out = f"{base}{sep}checkout_api={quote(api, safe='')}"
        cs = (MINIAPP_CHECKOUT_SECRET or "").strip()
        if cs:
            out += f"&checkout_secret={quote(cs, safe='')}"
        return out
    return base


def owner_telegram_id_int() -> int | None:
    if not OWNER_TELEGRAM_ID:
        return None
    try:
        return int(OWNER_TELEGRAM_ID)
    except ValueError:
        return None


def developer_telegram_id_int() -> int | None:
    """Telegram user id разработчика (команда /health). Пустое значение — не добавлять в список."""
    if not DEVELOPER_TELEGRAM_ID:
        return None
    try:
        return int(DEVELOPER_TELEGRAM_ID)
    except ValueError:
        return None


def admin_telegram_ids() -> set[int]:
    """
    Список Telegram user id, которым разрешён /admin (через запятую в .env).

    Пример: ADMIN_IDS=123456789,987654321
    """
    raw = _env("ADMIN_IDS", "")
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def health_command_allowed_user_ids() -> set[int]:
    """Кто может вызывать /health: владелец и (если задан) разработчик."""
    out: set[int] = set()
    o = owner_telegram_id_int()
    if o is not None:
        out.add(o)
    d = developer_telegram_id_int()
    if d is not None:
        out.add(d)
    return out


# Логирование (бот): LOG_LEVEL=DEBUG|INFO|WARNING|ERROR; LOG_FILE по умолчанию logs/bot.log
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
LOG_FILE_RAW = os.environ.get("LOG_FILE")
if LOG_FILE_RAW is None:
    LOG_FILE = "logs/bot.log"
else:
    LOG_FILE = LOG_FILE_RAW.strip()
    if LOG_FILE.lower() in ("none", "false", "-"):
        LOG_FILE = ""
