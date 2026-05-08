"""
Simple Telegram bot: list 16 tracks from tracks.py, show cover + text, buy link when set.

Run:  python bot.py

Needs in .env: BOT_TOKEN (and STRIPE_TOKEN if you add Stripe later).
Optional: MINIAPP_URL=https://.../miniapp.html (HTTPS) for the Music Store WebApp button.
"""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from music_sales.admin_panel import build_admin_conversation_handler

from tracks import TRACKS, get_track

load_dotenv()

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def _test_mode() -> bool:
    """TEST_MODE из .env: дешёвые цены и префикс [TEST] в сообщениях (читаем os при каждом вызове)."""
    v = (os.getenv("TEST_MODE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _test_banner_prefix() -> str:
    """Префикс в тексте, чтобы админ видел, что включён тестовый режим."""
    return "[TEST] " if _test_mode() else ""


def _detail_price_line(track: dict) -> str:
    """Строка цены для карточки: в тесте — из TEST_PRICE_USD, иначе из tracks.py."""
    if _test_mode():
        try:
            n = int((os.getenv("TEST_PRICE_USD") or "1").strip() or "1")
        except ValueError:
            n = 1
        return f"💰 Price: ${n} (test)"
    return f"💰 Price: {track['price']}"


def _miniapp_url() -> str:
    """HTTPS URL Mini App + query checkout_api (BACKEND_URL) для fetch create-checkout."""
    from urllib.parse import quote

    direct = (os.getenv("MINIAPP_URL") or "").strip()
    if direct.startswith("https://"):
        base = direct
    else:
        base_dom = (os.getenv("DOMAIN") or "").strip().rstrip("/")
        if base_dom.startswith("https://"):
            base = f"{base_dom}/miniapp.html"
        else:
            return ""
    api = (os.getenv("BACKEND_URL") or "").strip().rstrip("/")
    if api.startswith("https://"):
        sep = "&" if "?" in base else "?"
        out = f"{base}{sep}checkout_api={quote(api, safe='')}"
        cs = (os.getenv("MINIAPP_CHECKOUT_SECRET") or "").strip()
        if cs:
            out += f"&checkout_secret={quote(cs, safe='')}"
        return out
    return base

# Optional: Stripe secret for future checkout code (not used in this minimal bot).
_stripe = os.getenv("STRIPE_TOKEN", "").strip()


def _buy_keyboard(track: dict) -> InlineKeyboardButton:
    """Кнопка оплаты: в TEST_MODE — общая тестовая Stripe Payment Link, если задана в .env."""
    if _test_mode():
        test_url = (os.getenv("TEST_PAYMENT_LINK_USD") or "").strip()
        if test_url.startswith(("http://", "https://")):
            return InlineKeyboardButton("💳 Buy Now (test)", url=test_url)
    url = (track.get("buy_url") or "").strip()
    return (
        InlineKeyboardButton("💳 Buy Now", url=url)
        if url.startswith(("http://", "https://"))
        else InlineKeyboardButton("💳 Buy Now", callback_data="buy_unavailable")
    )


def _duration_line(track: dict) -> str | None:
    """Длительность MP3 в коротком виде (например 50m 8s), если файл есть и mutagen доступен."""
    try:
        from music_sales.catalog import project_root
        from music_sales.mp3_duration import format_duration_short, mp3_duration_seconds
    except ImportError:
        return None
    ap = project_root() / str(track.get("audio", "") or "")
    sec = mp3_duration_seconds(ap)
    return format_duration_short(sec)


def _detail_text(track: dict) -> str:
    """Текст карточки трека в детальном просмотре."""
    esc = html.escape
    prefix = esc(_test_banner_prefix())
    dur = _duration_line(track)
    dur_block = f"\n\n⏱ {esc(dur)}" if dur else ""
    return (
        f"{prefix}✨ {esc(track['title'])}\n\n"
        f"{esc(track['description'])}\n\n"
        f"{esc(_detail_price_line(track))}"
        f"{dur_block}"
    )


def _next_track_id(track_id: int) -> int:
    """Следующий трек по кругу по списку TRACKS (учитывает extras из tracks_extra.json)."""
    ids = [int(t["id"]) for t in TRACKS]
    if not ids:
        return track_id
    try:
        i = ids.index(int(track_id))
    except ValueError:
        return ids[0]
    return ids[(i + 1) % len(ids)]


def _track_card_keyboard(track: dict) -> InlineKeyboardMarkup:
    """Полная клавиатура: опционально Mini App + 16 кнопок треков + Buy + NEXT."""
    rows: list[list[InlineKeyboardButton]] = []
    store_url = _miniapp_url()
    if store_url:
        rows.append([InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=store_url))])
    for i in range(0, len(TRACKS), 2):
        left = TRACKS[i]
        row = [InlineKeyboardButton(left["short_title"], callback_data=str(left["id"]))]
        if i + 1 < len(TRACKS):
            right = TRACKS[i + 1]
            row.append(InlineKeyboardButton(right["short_title"], callback_data=str(right["id"])))
        rows.append(row)
    rows.append([_buy_keyboard(track)])
    rows.append([InlineKeyboardButton("NEXT", callback_data=f"next:{_next_track_id(track['id'])}")])
    return InlineKeyboardMarkup(rows)


async def _send_track_card(chat_id: int, track: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показываем одну карточку трека сверху с обложкой/описанием и общей клавиатурой."""
    try:
        cover_path = ROOT / track["cover"]
        text = _detail_text(track)
        markup = _track_card_keyboard(track)
        if cover_path.is_file():
            with cover_path.open("rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
        else:
            logger.warning("Cover not found for track %s: %s", track["id"], cover_path)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎵 {track['title']}\n\n{text}",
                parse_mode="HTML",
                reply_markup=markup,
            )
    except Exception:
        logger.exception("Failed to send track card for track_id=%s", track.get("id"))
        await context.bot.send_message(
            chat_id=chat_id,
            text="Something went wrong while loading the track. Please try again.",
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    # Первое сообщение в чате: только WebApp — пользователь сразу открывает витрину.
    store_url = _miniapp_url()
    if store_url:
        await update.message.reply_text(
            _test_banner_prefix() + "Welcome! Tap the button below to open the Music Store.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=store_url))]]
            ),
        )
    first_track = get_track(1)
    if first_track is None:
        await update.message.reply_text("No tracks available.")
        return
    await _send_track_card(update.message.chat.id, first_track, context)


async def on_track_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    logger.info("Callback clicked: %s", query.data)
    chat = query.message.chat if query.message else None
    if chat is None:
        return

    if query.data == "buy_unavailable":
        await context.bot.send_message(
            chat_id=chat.id,
            text="Payment link is not set yet. Please contact support.",
        )
        return

    try:
        if query.data.startswith("next:"):
            tid = int(query.data.split(":", 1)[1])
        elif query.data.isdigit():
            tid = int(query.data)
        else:
            return
        track = get_track(tid)
        if track is None:
            await context.bot.send_message(chat_id=chat.id, text="Unknown track.")
            return
        # Удаляем прошлую карточку, чтобы сверху всегда оставалась только одна актуальная.
        if query.message is not None:
            try:
                await query.message.delete()
            except Exception:
                logger.warning("Could not delete previous track card message")
        await _send_track_card(chat.id, track, context)
    except Exception:
        logger.exception("Failed to process track callback: %s", query.data)
        await context.bot.send_message(
            chat_id=chat.id,
            text="Something went wrong while opening this track. Please try again.",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if err is not None:
        logger.error("Update caused error", exc_info=err)
    else:
        logger.error("Update caused error (no context.error)")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN in .env (see comments in .env file).")

    if _stripe:
        logger.info("STRIPE_TOKEN is set (ready if you add payment code).")
    else:
        logger.info("STRIPE_TOKEN not set — only needed when you connect Stripe.")
    if _test_mode():
        logger.warning("TEST_MODE is ON — reduced prices and TEST_PAYMENT_LINK_USD if set.")

    app = Application.builder().token(token).build()
    app.add_handler(build_admin_conversation_handler())
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_track_button, pattern=r"^(buy_unavailable|\d+|next:\d+)$"))
    app.add_error_handler(error_handler)
    logger.info("Bot polling…")
    app.run_polling()


if __name__ == "__main__":
    main()
