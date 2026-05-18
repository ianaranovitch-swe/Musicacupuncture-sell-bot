from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    MenuButtonWebApp,
    Update,
    User,
    WebAppInfo,
    InputFile,
)
from telegram.ext import ContextTypes

from music_sales import config
from music_sales.about_michael import (
    ABOUT_MICHAEL_BODY,
    ABOUT_MICHAEL_PHOTO_CAPTION,
    existing_about_michael_photos,
)
from music_sales.file_id_delivery import load_file_ids_dict
from music_sales.free_track_cover_render import render_free_track_cover_for_telegram
from music_sales.owner_notify import notify_owner_async
from music_sales.sales_log import append_free_download_event
from music_sales.admin_panel import is_admin, offer_admin_reply_keyboard
from music_sales.testimonials_bot import main_menu_reviews_button_row, random_start_testimonial_blurb

logger = logging.getLogger(__name__)

FREE_TRACK_TITLE = "Divine sound Super Feng Shui from God"
FREE_TRACK_GALLERY_COVERS = [
    "covers/Divine-sound-Super-Feng-Shui-from-God.png",
    "covers/Divine sound Super Feng Shui from God CD cover front.png",
    "covers/Divine sound Super Feng Shui from God CD cover back.png",
]
FREE_TRACK_CB = "gift:free_track"
FREE_TRACK_START_PAYLOAD = "gift_free_track"
ABOUT_MICHAEL_CB = "about:michael"
ABOUT_MICHAEL_BUTTON_TEXT = "About Michael — Founder of MusicAcupuncture®"


async def notify_owner_about_visitor(context: ContextTypes.DEFAULT_TYPE, visitor: User) -> None:
    """Отправить владельцу событие о запуске бота без показа ID пользователя."""
    await notify_owner_async(
        context,
        actor=visitor,
        event="Bot started",
    )


def _miniapp_store_row(*, url_override: str | None = None) -> list[InlineKeyboardButton] | None:
    """Одна строка с Mini App, если задан валидный HTTPS URL (требование Telegram)."""
    url = (url_override or config.resolved_miniapp_url()).strip()
    if not url.startswith("https://"):
        return None
    return [InlineKeyboardButton("🎵 Open Music Store", web_app=WebAppInfo(url=url))]


def _about_michael_button_row() -> list[InlineKeyboardButton]:
    """About Michael только в чате бота (без ссылки на website)."""
    return [
        InlineKeyboardButton(
            ABOUT_MICHAEL_BUTTON_TEXT,
            callback_data=ABOUT_MICHAEL_CB,
        )
    ]


def _free_track_markup() -> InlineKeyboardMarkup:
    """Главное меню /start: подарок, отзывы, About."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🎁 Get Free Track", callback_data=FREE_TRACK_CB)],
        main_menu_reviews_button_row(),
    ]
    rows.append(_about_michael_button_row())
    return InlineKeyboardMarkup(rows)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


async def send_free_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик кнопки бесплатного трека.

    Шаги:
    1) отправляем обложку;
    2) отправляем описание подарка;
    3) отправляем MP3 по file_id из FILE_IDS_JSON;
    4) показываем каталог (Mini App).
    """
    # Может быть вызвано либо кнопкой (callback_query), либо deep-link /start gift_free_track (message).
    query = update.callback_query
    if query is not None:
        try:
            await query.answer()
        except Exception:
            pass
    chat_id = None
    if query is not None and query.message:
        chat_id = query.message.chat_id
    elif update.effective_chat is not None:
        chat_id = update.effective_chat.id
    elif update.message is not None and getattr(update.message, "chat_id", None) is not None:
        chat_id = update.message.chat_id
    if chat_id is None:
        return

    root = _repo_root()
    # 1-я обложка — уже круглый PNG с альфой из Photoshop, шлём как есть (без повторного «вырезания» круга).
    # 2–3 — фото футляра: при желании вписываем в квадрат с фоном как в Mini App (см. render…case_square).
    for index, rel_path in enumerate(FREE_TRACK_GALLERY_COVERS):
        cover_path = root / rel_path
        if not cover_path.is_file():
            continue
        try:
            if index == 0:
                with cover_path.open("rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo)
                continue
            png_bytes = render_free_track_cover_for_telegram(cover_path, "case_square")
            if png_bytes:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=InputFile(BytesIO(png_bytes), filename=f"free_track_cover_{index}.png"),
                )
            else:
                with cover_path.open("rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo)
        except Exception:
            # Фото не критично: продолжаем выдачу.
            pass

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎁 Your FREE gift from Michael!\n"
            f"✨ {FREE_TRACK_TITLE}\n\n"
            "This divine sound supports harmony,\n"
            "balance and positive energy flow in\n"
            "your home and life.\n\n"
            "Listen daily for best results. 🙏\n\n"
            "Enjoy the other 17 healing tracks below 👇"
        ),
    )

    file_ids = load_file_ids_dict()
    fid = file_ids.get(FREE_TRACK_TITLE)
    if not fid:
        # Подсказка администратору: нужно загрузить файл через upload_songs.py.
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, the free track is not available right now. Please contact support.",
        )
    else:
        await context.bot.send_document(
            chat_id=chat_id,
            document=fid,
            caption="🎁 Free bonus track — enjoy! 🙏",
        )
        # Логируем бесплатную выдачу, чтобы видеть метрику FREE DOWNLOADS в /admin.
        append_free_download_event(
            telegram_user_id=int(chat_id),
            track_title=FREE_TRACK_TITLE,
        )

    row = _miniapp_store_row()
    if row:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Open the Music Store to explore the other tracks:",
            reply_markup=InlineKeyboardMarkup([row]),
        )

async def _send_miniapp_store_opener_if_configured(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Первое сообщение при /start: кнопка WebApp (тексты UI на английском)."""
    if update.message is None:
        return
    row = _miniapp_store_row()
    if not row:
        return
    # Ставим WebApp в меню чата: так пользователь открывает магазин без лишних сообщений-кнопок в чате.
    try:
        url = config.resolved_miniapp_url()
        # Добавляем bot_username в URL, чтобы Mini App смог открыть чат и выдать бесплатный подарок.
        try:
            me = await context.bot.get_me()
            uname = (me.username or "").strip().lstrip("@")
        except Exception:
            uname = ""
        if uname:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}bot_username={uname}"
        row = _miniapp_store_row(url_override=url) or row
        if url.startswith("https://"):
            await context.bot.set_chat_menu_button(
                chat_id=update.message.chat_id,
                menu_button=MenuButtonWebApp(
                    text="Music Store",
                    web_app=WebAppInfo(url=url),
                ),
            )
    except Exception:
        # Меню-кнопка не критична: если не получилось — покажем обычную inline-кнопку.
        pass

    welcome = "Welcome! Open the Music Store from the menu button."
    if config.test_mode_active():
        welcome = "[TEST] " + welcome
    rows = [row, _about_michael_button_row()]
    await update.message.reply_text(
        welcome,
        # Inline-кнопку оставляем как fallback (на случай, если MenuButton не поддержан в клиенте/ошибка API).
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    # Deep-link: если открыли бота из Mini App для подарка, выдаём сразу.
    txt = update.message.text
    if isinstance(txt, str) and txt.strip().startswith(f"/start {FREE_TRACK_START_PAYLOAD}"):
        await send_free_track(update, context)
        return
    # Приветствие + бесплатный подарок.
    await update.message.reply_text(
        "🎁 Special gift from Michael!\n\n"
        "Receive a FREE healing track:\n"
        f"✨ {FREE_TRACK_TITLE}\n\n"
        "This is our gift to you — no payment needed!\n"
        "Experience the power of Music Acupuncture.",
        reply_markup=_free_track_markup(),
    )
    blurb, blurb_markup = random_start_testimonial_blurb()
    if blurb:
        await update.message.reply_text(blurb, reply_markup=blurb_markup)
    await _send_miniapp_store_opener_if_configured(update, context)
    user = update.effective_user
    if user is not None:
        logger.info("/start from user_id=%s username=%s", user.id, user.username or "-")
        await notify_owner_about_visitor(context, user)
    if user is not None and is_admin(user.id):
        await offer_admin_reply_keyboard(update, context)
    if not _miniapp_store_row():
        await update.message.reply_text(
            "Music Store is not configured yet. Ask admin to set MINIAPP_URL (HTTPS) and BACKEND_URL."
        )


async def _send_about_michael_photos(chat_id: int, context: ContextTypes.DEFAULT_TYPE, photo_paths: list[Path]) -> None:
    """Одно фото или альбом (до 10) — подпись только у первого снимка."""
    if len(photo_paths) == 1:
        with photo_paths[0].open("rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=ABOUT_MICHAEL_PHOTO_CAPTION,
            )
        return

    handles: list = []
    media: list[InputMediaPhoto] = []
    try:
        for i, path in enumerate(photo_paths):
            fh = path.open("rb")
            handles.append(fh)
            cap = ABOUT_MICHAEL_PHOTO_CAPTION if i == 0 else None
            media.append(InputMediaPhoto(media=fh, caption=cap))
        await context.bot.send_media_group(chat_id=chat_id, media=media)
    finally:
        for fh in handles:
            fh.close()


def _about_michael_chat_id(update: Update) -> int | None:
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message.chat_id
    if update.message is not None:
        return update.message.chat_id
    if update.effective_chat is not None:
        return update.effective_chat.id
    return None


async def send_about_michael(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Портрет(ы) + полный текст About Michael — только в Telegram."""
    query = update.callback_query
    if query is not None:
        try:
            await query.answer()
        except Exception:
            pass

    chat_id = _about_michael_chat_id(update)
    if chat_id is None:
        return

    root = _repo_root()
    photo_paths = existing_about_michael_photos(root)
    try:
        if photo_paths:
            await _send_about_michael_photos(chat_id, context, photo_paths)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Photo files are not deployed yet. Ask admin to add assets/about-michael.png "
                    "(and about-michael-2.png) to the server."
                ),
            )
    except Exception:
        logger.exception("send_about_michael: send photos failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Could not send the portrait images. Full biography below.",
        )
    await context.bot.send_message(chat_id=chat_id, text=ABOUT_MICHAEL_BODY)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /about: портрет(ы) + полный текст в чате."""
    if update.message is None:
        return
    await send_about_michael(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Краткая справка: у бота остался только Mini App сценарий."""
    if update.message is None:
        return

    lines = [
        "This bot sells MP3 tracks via the Mini App and sends paid audio in Telegram.",
        "",
        "Commands:",
        "• /start — open the Music Store Mini App",
        "• /about — founder biography (Michael B. Johnsson)",
        "• ⭐ Customer Reviews — on /start (browse all reviews)",
        "• /help — show this help message",
        "• /health — owner/developer diagnostics only",
    ]
    if update.effective_user and is_admin(update.effective_user.id):
        lines.extend(
            [
                "",
                "Admin:",
                "• /admin — admin panel",
                "• 🔐 Admin — same panel (button at the bottom of the chat)",
            ]
        )
    lines.extend(
        [
            "",
            "How to buy:",
            "1) Open /start",
            "2) Choose a track and currency in the Mini App",
            "3) Tap Buy and complete Stripe checkout",
            "",
            "Tip: if checkout opened in background, tap Buy again and open the latest checkout link/button.",
        ]
    )
    await update.message.reply_text("\n".join(lines))
