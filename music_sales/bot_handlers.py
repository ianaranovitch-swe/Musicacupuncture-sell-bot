from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    MenuButtonWebApp,
    ReplyParameters,
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
    existing_about_michael_video,
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
# ID сообщений с обложками бесплатного трека в этом чате (чтобы не слать дубликаты).
CHAT_DATA_FREE_TRACK_GALLERY_MSG_IDS = "free_track_gallery_message_ids"
ABOUT_MICHAEL_CB = "about:michael"
ABOUT_MICHAEL_BUTTON_TEXT = "About Michael — Founder of MusicAcupuncture®"
ABOUT_VIDEO_SOUND_CB = "about:video_sound"


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


def _free_track_trigger_reply_parameters(update: Update) -> ReplyParameters | None:
    """Ответ на сообщение с кнопкой Get Free Track — контент сразу под кликом."""
    if update.callback_query is not None and update.callback_query.message is not None:
        msg = update.callback_query.message
    elif update.message is not None:
        msg = update.message
    else:
        return None
    return ReplyParameters(message_id=msg.message_id, allow_sending_without_reply=True)


def _expected_free_track_cover_count(root: Path) -> int:
    return sum(1 for rel in FREE_TRACK_GALLERY_COVERS if (root / rel).is_file())


def _free_track_gallery_is_complete(context: ContextTypes.DEFAULT_TYPE, root: Path) -> bool:
    expected = _expected_free_track_cover_count(root)
    if expected <= 0:
        return False
    stored = context.chat_data.get(CHAT_DATA_FREE_TRACK_GALLERY_MSG_IDS)
    if not isinstance(stored, list):
        return False
    return len(stored) >= expected


def _free_track_gallery_reply_parameters(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    trigger_reply: ReplyParameters | None,
) -> ReplyParameters | None:
    """Повторный клик: ответ на последнюю обложку (фокус на уже отправленные картинки)."""
    stored = context.chat_data.get(CHAT_DATA_FREE_TRACK_GALLERY_MSG_IDS)
    if isinstance(stored, list) and stored:
        return ReplyParameters(message_id=int(stored[-1]), allow_sending_without_reply=True)
    return trigger_reply


async def _send_free_track_gallery_covers(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    root: Path,
    *,
    reply_params: ReplyParameters | None,
) -> list[int]:
    """Шлём обложки один раз; возвращаем message_id для chat_data."""
    message_ids: list[int] = []
    for index, rel_path in enumerate(FREE_TRACK_GALLERY_COVERS):
        cover_path = root / rel_path
        if not cover_path.is_file():
            continue
        try:
            if index == 0:
                with cover_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_parameters=reply_params,
                    )
            else:
                png_bytes = render_free_track_cover_for_telegram(cover_path, "case_square")
                if png_bytes:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=InputFile(BytesIO(png_bytes), filename=f"free_track_cover_{index}.png"),
                        reply_parameters=reply_params,
                    )
                else:
                    with cover_path.open("rb") as photo:
                        sent = await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            reply_parameters=reply_params,
                        )
            message_ids.append(sent.message_id)
        except Exception:
            pass
    if message_ids:
        context.chat_data[CHAT_DATA_FREE_TRACK_GALLERY_MSG_IDS] = message_ids
    return message_ids


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
    trigger_reply = _free_track_trigger_reply_parameters(update)
    gallery_complete = _free_track_gallery_is_complete(context, root)

    if not gallery_complete:
        await _send_free_track_gallery_covers(
            chat_id, context, root, reply_params=trigger_reply
        )
        content_reply = _free_track_gallery_reply_parameters(context, trigger_reply=trigger_reply)
    else:
        content_reply = _free_track_gallery_reply_parameters(context, trigger_reply=trigger_reply)

    gift_lines = [
        "🎁 Your FREE gift from Michael!",
        f"✨ {FREE_TRACK_TITLE}",
        "",
        "This divine sound supports harmony,",
        "balance and positive energy flow in",
        "your home and life.",
        "",
        "Listen daily for best results. 🙏",
        "",
        "Enjoy the other 17 healing tracks below 👇",
    ]
    if gallery_complete:
        gift_lines.insert(1, "Your free track covers are already shown above ↑")

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(gift_lines),
        reply_parameters=content_reply,
    )

    row = _miniapp_store_row()
    if row:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Open the Music Store to explore the other tracks:",
            reply_markup=InlineKeyboardMarkup([row]),
            reply_parameters=content_reply,
        )

    file_ids = load_file_ids_dict()
    fid = file_ids.get(FREE_TRACK_TITLE)
    if not fid:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, the free track is not available right now. Please contact support.",
            reply_parameters=content_reply,
        )
    else:
        await context.bot.send_document(
            chat_id=chat_id,
            document=fid,
            caption="🎁 Free bonus track — enjoy! 🙏",
            reply_parameters=content_reply,
        )
        append_free_download_event(
            telegram_user_id=int(chat_id),
            track_title=FREE_TRACK_TITLE,
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


def _about_reply_parameters(update: Update) -> ReplyParameters | None:
    """
    Ответ в цепочке к сообщению с кнопкой — чат прокручивается к About Michael сразу под кликом.
    """
    msg = None
    if update.callback_query is not None and update.callback_query.message is not None:
        msg = update.callback_query.message
    elif update.message is not None:
        msg = update.message
    if msg is None:
        return None
    return ReplyParameters(message_id=msg.message_id, allow_sending_without_reply=True)


def _about_video_sound_markup() -> InlineKeyboardMarkup:
    """Звук: HTTPS-ссылка на MP4 (надёжно) или callback для локальной разработки."""
    base = (config.BACKEND_URL or "").strip().rstrip("/")
    if base.startswith("https://"):
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔊 Turn sound on",
                        url=f"{base}/assets/michael.mp4",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "▶️ Play with sound in chat",
                        callback_data=ABOUT_VIDEO_SOUND_CB,
                    )
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔊 Turn sound on", callback_data=ABOUT_VIDEO_SOUND_CB)]]
    )


async def _send_about_michael_icon_video(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    video_path: Path,
    *,
    reply_params: ReplyParameters | None = None,
) -> None:
    """Иконка бота (MP4): animation без звука; кнопка звука — отдельным сообщением."""
    with video_path.open("rb") as video:
        await context.bot.send_animation(
            chat_id=chat_id,
            animation=video,
            reply_parameters=reply_params,
        )
    await context.bot.send_message(
        chat_id=chat_id,
        text="🔊 Tap below to play the icon video with sound:",
        reply_markup=_about_video_sound_markup(),
        reply_parameters=reply_params,
    )


async def about_video_sound_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """По кнопке — MP4 как video в чате (со звуком в плеере Telegram)."""
    query = update.callback_query
    if query is None or query.message is None:
        return
    chat_id = query.message.chat_id
    reply_params = ReplyParameters(
        message_id=query.message.message_id,
        allow_sending_without_reply=True,
    )
    try:
        await query.answer()
    except Exception:
        pass
    video_path = existing_about_michael_video(_repo_root())
    if video_path is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Video file is not available on the server.",
            reply_parameters=reply_params,
        )
        return
    try:
        with video_path.open("rb") as video_file:
            await context.bot.send_video(
                chat_id=chat_id,
                video=InputFile(video_file, filename="michael.mp4"),
                caption="Tap ▶️ on the video to play with sound.",
                supports_streaming=True,
                reply_parameters=reply_params,
            )
    except Exception:
        logger.exception("about_video_sound_callback: send_video failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Could not send the video with sound. Try the HTTPS link button above.",
            reply_parameters=reply_params,
        )


async def _send_about_michael_photos(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    photo_paths: list[Path],
    *,
    reply_params: ReplyParameters | None = None,
) -> None:
    """Одно фото или альбом (до 10) — подпись только у первого снимка."""
    if len(photo_paths) == 1:
        with photo_paths[0].open("rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=ABOUT_MICHAEL_PHOTO_CAPTION,
                reply_parameters=reply_params,
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
        await context.bot.send_media_group(
            chat_id=chat_id,
            media=media,
            reply_parameters=reply_params,
        )
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

    reply_params = _about_reply_parameters(update)
    root = _repo_root()
    video_path = existing_about_michael_video(root)
    photo_paths = existing_about_michael_photos(root)

    # Якорь под кнопкой — сразу видно начало блока About Michael.
    await context.bot.send_message(
        chat_id=chat_id,
        text="About Michael — Founder of MusicAcupuncture®",
        reply_parameters=reply_params,
    )

    if video_path is not None:
        try:
            await _send_about_michael_icon_video(
                chat_id, context, video_path, reply_params=reply_params
            )
        except Exception:
            logger.exception("send_about_michael: send icon video failed")
    try:
        if photo_paths:
            await _send_about_michael_photos(
                chat_id, context, photo_paths, reply_params=reply_params
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Photo files are not deployed yet. Ask admin to add assets/about-michael.png "
                    "(and about-michael-2.png) to the server."
                ),
                reply_parameters=reply_params,
            )
    except Exception:
        logger.exception("send_about_michael: send photos failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Could not send the portrait images. Full biography below.",
            reply_parameters=reply_params,
        )
    await context.bot.send_message(
        chat_id=chat_id,
        text=ABOUT_MICHAEL_BODY,
        reply_parameters=reply_params,
    )


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
