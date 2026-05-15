"""Каталог из 18 встроенных треков (обложка и MP3 — см. поля cover / audio).

Поле buy_url_sek — ссылка Stripe для Mini App в SEK (может совпадать с buy_url).
Опционально: is_featured, is_new, ui_emoji, ui_short_name — для витрины и фронта.
Опционально: google_drive_file_id — ID файла в Google Drive для скачивания с сайта после Stripe (файлы >20 MB).
Нужен GOOGLE_SERVICE_ACCOUNT_JSON и доступ SA к папке с MP3. См. _BUILTIN_GOOGLE_DRIVE_IDS.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path


def _test_mode_env_on() -> bool:
    """Совпадает с music_sales.config.test_mode_active() — без импорта config из tracks (порядок загрузки)."""
    v = (os.environ.get("TEST_MODE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _test_payment_link_for_all_tracks() -> str | None:
    """
    Один тестовый Payment Link для всех платных треков (Stripe test mode).
    Приоритет: TEST_PAYMENT_LINK → TEST_PAYMENT_LINK_USD (как в bot.py).
    """
    if not _test_mode_env_on():
        return None
    link = (os.environ.get("TEST_PAYMENT_LINK") or "").strip()
    if link:
        return link
    return (os.environ.get("TEST_PAYMENT_LINK_USD") or "").strip() or None


# Google Drive file IDs для website / Stripe download (все 18 MP3, включая бесплатный id 18).
_BUILTIN_GOOGLE_DRIVE_IDS: dict[int, str] = {
    1: "1v4Tv0LGcgvlHEYDq4gTapVYnlbt5560O",
    2: "1zwat55udeiJD5aEIpQ3YLJKGTYuKHGJI",
    3: "12B0RmB4ViwJIi916Aowy32t7T5hTvqqi",
    4: "1BH6Y2Ad8UrUrCrQoXW-eAl7f32QAaVFu",
    5: "1Gpk8D-gfs6O2IoKthEVJ-Aj1KPwWNdIB",
    6: "1hdM8b5UnImkSJAxfymO4pKeDneWlnuii",
    7: "10mqVlA0bvt9SUTcwHIoJNzHujK-7-Bh6",
    8: "1BeBfmzXkEJh4svFHNHzsFopUnzIs-eff",
    9: "18lVS9P7ZbEKxAr1qta4WHeDr9lr5mtbt",
    10: "1YK5IrCmThG9np6xVurr3EWa5vSaEUDyW",
    11: "1v3r70B0mr7i_fJZltQS3LpRaJSChskjd",
    12: "14J_-gDqrmhbAy--Z-2_5wuMqzNfVd1ur",
    13: "10jWeAvLxS69qqZ7oyVcHorCuqTUe2FpV",
    14: "1l9EjCgfLZ0910LsVRZzpmwy9bJDTsEN8",
    15: "1v3kf1uH4kAva5WQZgmTVWNDk_QHCDpYZ",
    16: "1nqBnWYr8EcJhVJTSP2BMQirx5gXie-2A",
    17: "10GwbO5VBYUnvsCiLHDTKKDAFR_d-uVU7",
    18: "1Ic-8UEK9o9B7X0f1Ve0r0fTxpg08iG84",
}

# Встроенный каталог (редактируется в репозитории). Админка добавляет слои через JSON рядом с файлом.
_BUILTIN_TRACKS: list[dict] = [
    # Порядок для клавиатуры бота: сначала бесплатный, сразу новый релиз, дальше остальные (Mini App/сайт — см. ordered_frontend_pairs).
    {
        "id": 18,
        "short_title": "🎁 Free Gift",
        "title": "Divine sound Super Feng Shui from God",
        "description": (
            "THIS SUPER FENG SHUI - SPACE CLEARING-MP3 IS ONE OF THE MOST POWERFUL TREATMENTS FOR ROOM AND SPACE. "
            "IT IS ALSO ONE OF THE EASIEST AND FASTEST WAYS TO ACHIEVE A GOOD RESULT. "
            "APART FROM ITS ABILITY TO BALANCE ROOM AND SPACE, YOU CAN ALSO ADD ONE MORE DIMENSION: "
            "THE HARMONY AND HEALTH IT GIVES TO YOURSELF.\n\n"
            "Feng Shui is the oriental art of enhancing and harmonizing the flow of energy in your surroundings. "
            "Discover how Feng Shui can bring harmony and prosperity into your life, neutralize negative influences "
            "in your house and create a healthy and positive living and working space. "
            "You can create an environment that directly embraces and empowers your life."
        ),
        "price": "FREE",
        "price_amount": 0,
        "cover": "covers/Divine-sound-Super-Feng-Shui-from-God.png",
        "audio": "songs/Divine sound Super Feng Shui from God.mp3",
        "buy_url": "",
        "buy_url_sek": ""
    },
    {
        "id": 17,
        "short_title": "🌙 ✨NEW✨ Sleep Best Silver Power",
        "title": "Divine sound Sleep Best Silver Power from God",
        "description": (
            "🌙 The latest masterpiece from Soundmaster Mikael.\n\n"
            "Struggling to relax and feel truly restored?\n"
            "SLEEP BEST – Earth Grounding Silver Power is a "
            "rare and exclusive healing audio experience, "
            "crafted to release deep stress, reconnect your "
            "body with calming earth energy, and guide you "
            "into profound natural rest.\n\n"
            "As you listen, a soft silver energy connects you "
            "to the Earth… calming your thoughts… restoring "
            "your natural rhythm… and carrying you into "
            "stillness like never before.\n\n"
            "✨ What you may experience:\n"
            "• Deeper, more peaceful sleep from night one\n"
            "• Full-body relaxation and grounding\n"
            "• Calm energy flowing through mind and body\n"
            "• Waking up refreshed and restored\n\n"
            "💫 Perfect for nighttime relaxation, meditation "
            "before sleep, and stress relief after a long day.\n\n"
            "🎧 Close your eyes. Breathe slowly. Let go.\n\n"
            "This is Mikael's most powerful creation yet."
        ),
        "price": "$16",
        "price_sek": "169 kr",
        "price_amount": 1600,
        "currency": "USD",
        "cover": "covers/Divine sound Sleep Best Silver Power from God.png",
        "audio": "songs/Divine sound Sleep Best Silver Power from God.mp3",
        "buy_url": "https://buy.stripe.com/7sY7sK8fz1Of7XfdcBcfK0i",
        "buy_url_sek": "https://buy.stripe.com/7sY7sK8fz1Of7XfdcBcfK0i",
        "is_featured": True,
        "is_new": True,
        "ui_emoji": "🌙",
        "ui_short_name": "Sleep Best Silver Power",
    },
    {
        "id": 1,
        "short_title": "🎵 Crown Chakra",
        "title": "Divine sound Crownchakra-Browchakra-Throatchakra from God",
        "description": (
            "Speak your truth with calm, clarity, and confidence.\n"
            "Clear, uplifting frequencies to support communication and self-expression. "
            "Helps you speak your truth with confidence and calm. Encourages authentic voice "
            "and inner clarity. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Crownchakra-Browchakra-Throatchakra-from-God.png",
        "audio": "songs/Divine sound Crownchakra-Browchakra-Throatchakra from God.mp3",
        "buy_url": "https://buy.stripe.com/28E3cubrLcsT2CV5K9cfK00",
        "buy_url_sek": "https://buy.stripe.com/28E3cubrLcsT2CV5K9cfK00"
    },
    {
        "id": 2,
        "short_title": "🎵 Estrogen",
        "title": "Divine sound Estrogen from God",
        "description": (
            "Support feminine balance, harmony, and natural flow.\n"
            "Gentle frequencies designed to support feminine hormonal balance and well-being. "
            "Encourages harmony, vitality, and inner softness. Ideal for restoring natural flow "
            "and emotional balance. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Estrogen-from-God.png",
        "audio": "songs/Divine sound Estrogen from God.mp3",
        "buy_url": "https://buy.stripe.com/6oU4gy0N78cDa5ngoNcfK02",
        "buy_url_sek": "https://buy.stripe.com/6oU4gy0N78cDa5ngoNcfK02"
    },
    {
        "id": 3,
        "short_title": "🎵 Heart",
        "title": "Divine sound Heart from God",
        "description": (
            "Open your heart to love, peace, and deep inner harmony.\n"
            "Healing vibrations designed to support your heart with love, emotional balance, "
            "and inner peace. Encourages harmony, circulation, and a deep sense of calm. "
            "A beautiful daily practice to awaken heart energy and connect with divine love. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Heart-from-God.png",
        "audio": "songs/Divine sound Heart from God.mp3",
        "buy_url": "https://buy.stripe.com/28EeVcanHakL4L3a0pcfK03",
        "buy_url_sek": "https://buy.stripe.com/28EeVcanHakL4L3a0pcfK03"
    },
    {
        "id": 4,
        "short_title": "🎵 Heart Chakra",
        "title": "Divine sound Heartchakra and Diaphragmchakra from God",
        "description": (
            "Expand love, compassion, and connection in your life.\n"
            "Loving vibrations to open compassion, forgiveness, and connection. "
            "Supports emotional healing and deeper relationships. "
            "A gentle expansion of love within and around you. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Heartchakra-and-Diaphragmchakra-from-God.png",
        "audio": "songs/Divine sound Heartchakra and Diaphragmchakra from God.mp3",
        "buy_url": "https://buy.stripe.com/dRm28qeDX9gH5P70pPcfK04",
        "buy_url_sek": "https://buy.stripe.com/dRm28qeDX9gH5P70pPcfK04"
    },
    {
        "id": 5,
        "short_title": "🎵 Immune Defence",
        "title": "Divine sound Immunedefence from God",
        "description": (
            "Strengthen your body's natural protection and inner power.\n"
            "Powerful sound frequencies created to strengthen your immune system and natural "
            "protection. Supports balance, resilience, and inner strength. Ideal for daily "
            "listening to help your body stay centered, protected, and energized. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Immunedefence-from-God.png",
        "audio": "songs/Divine sound Immunedefence from God.mp3",
        "buy_url": "https://buy.stripe.com/14AdR8dzTcsTb9rfkJcfK05",
        "buy_url_sek": "https://buy.stripe.com/14AdR8dzTcsTb9rfkJcfK05"
    },
    {
        "id": 6,
        "short_title": "🎵 Kidney",
        "title": "Divine sound Kidney from God",
        "description": (
            "Restore balance, flow, and deep inner stability.\n"
            "Balancing frequencies supporting kidney energy, cleansing, and inner stability. "
            "Encourages deep relaxation and energetic detox. A soothing sound journey that helps "
            "restore flow, grounding, and harmony in your whole body. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Kidney-from-God.png",
        "audio": "songs/Divine sound Kidney from God.mp3",
        "buy_url": "https://buy.stripe.com/dRm5kCbrLboPgtL7ShcfK06",
        "buy_url_sek": "https://buy.stripe.com/dRm5kCbrLboPgtL7ShcfK06"
    },
    {
        "id": 7,
        "short_title": "🎵 Liver",
        "title": "Divine sound Liver from God",
        "description": (
            "Cleanse, renew, and bring clarity to your whole body.\n"
            "Harmonizing vibrations designed to support liver energy and natural detox processes. "
            "Encourages renewal, clarity, and emotional release. Helps your body feel lighter, "
            "cleaner, and more balanced through daily listening. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Liver-from-God.png",
        "audio": "songs/Divine sound Liver from God.mp3",
        "buy_url": "https://buy.stripe.com/28E8wO53ndwX4L3b4tcfK07",
        "buy_url_sek": "https://buy.stripe.com/28E8wO53ndwX4L3b4tcfK07"
    },
    {
        "id": 8,
        "short_title": "🎵 Lungs",
        "title": "Divine sound Lungs from God",
        "description": (
            "Breathe deeper, relax fully, and awaken your life energy.\n"
            "Gentle healing vibrations for lungs and breathing. Supports deeper breath, "
            "relaxation, and life energy flow. Helps release stress and open the body to clarity, "
            "calmness, and renewed vitality through conscious listening. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Lungs-from-God.png",
        "audio": "songs/Divine sound Lungs from God.mp3",
        "buy_url": "https://buy.stripe.com/14AfZg67rgJ96TbegFcfK08",
        "buy_url_sek": "https://buy.stripe.com/14AfZg67rgJ96TbegFcfK08"
    },
    {
        "id": 9,
        "short_title": "🎵 Minerals",
        "title": "Divine sound Minerals from God",
        "description": (
            "Restore balance, strength, and deep cellular harmony.\n"
            "Grounding frequencies created to support your body's mineral balance and inner stability. "
            "Encourages strength, resilience, and deep cellular harmony. Helps your body feel "
            "supported, balanced, and naturally energized through consistent listening. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Minerals-from-God.png",
        "audio": "songs/Divine sound Minerals from God.mp3",
        "buy_url": "https://buy.stripe.com/cNidR88fzgJ9cdv6OdcfK09",
        "buy_url_sek": "https://buy.stripe.com/cNidR88fzgJ9cdv6OdcfK09"
    },
    {
        "id": 10,
        "short_title": "🎵 NO Alcohol",
        "title": "Divine sound NO Alcohol from God",
        "description": (
            "Release alcohol and return to clarity and control.\n"
            "Gentle yet powerful frequencies to support freedom from alcohol. Helps calm urges, "
            "restore inner balance, and strengthen self-control. A daily sound practice guiding you "
            "toward clarity, peace, and a healthier, more conscious lifestyle. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-NO-Alcohol-from-God.png",
        "audio": "songs/Divine sound NO Alcohol from God.mp3",
        "buy_url": "https://buy.stripe.com/28E8wOgM5akLa5n5K9cfK0b",
        "buy_url_sek": "https://buy.stripe.com/28E8wOgM5akLa5n5K9cfK0b"
    },
    {
        "id": 11,
        "short_title": "🎵 NO Smoking",
        "title": "Divine sound NO Smoking from God",
        "description": (
            "Break free from smoking and reclaim your health.\n"
            "Supportive healing vibrations designed to help release the habit of smoking. "
            "Encourages inner strength, calmness, and control over cravings. Helps reprogram your "
            "mind and body toward freedom, clarity, and a healthier, smoke-free life. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-NO-Smoking-from-God.png",
        "audio": "songs/Divine sound NO Smoking from God.mp3",
        "buy_url": "https://buy.stripe.com/dRm4gy7bv1Of4L37ShcfK0a",
        "buy_url_sek": "https://buy.stripe.com/dRm4gy7bv1Of4L37ShcfK0a"
    },
    {
        "id": 12,
        "short_title": "🎵 Root Chakra",
        "title": "Divine sound Rootchakra from God",
        "description": (
            "Feel grounded, safe, and strong in your foundation.\n"
            "Grounding frequencies to strengthen stability, safety, and physical energy. "
            "Supports connection to the earth and inner security. Ideal for building a strong "
            "foundation in body and life. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Rootchakra-from-God.png",
        "audio": "songs/Divine sound Rootchakra from God.mp3",
        "buy_url": "https://buy.stripe.com/cNieVc7bv0KbfpH8WlcfK0c",
        "buy_url_sek": "https://buy.stripe.com/cNieVc7bv0KbfpH8WlcfK0c"
    },
    {
        "id": 13,
        "short_title": "🎵 Sacral & Navel Chakra",
        "title": "Divine sound Sacralchakra and Navelchakra from God",
        "description": (
            "Awaken joy, creativity, and emotional flow.\n"
            "Flowing vibrations to awaken creativity, joy, and emotional balance. Supports sensual "
            "energy, inspiration, and positive life force. Helps you reconnect with pleasure and "
            "inner movement. Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Sacralchakra-and-Navelchakra-from-God.png",
        "audio": "songs/Divine sound Sacralchakra and Navelchakra from God.mp3",
        "buy_url": "https://buy.stripe.com/aFaaEWcvPgJ9dhz4G5cfK0d",
        "buy_url_sek": "https://buy.stripe.com/aFaaEWcvPgJ9dhz4G5cfK0d"
    },
    {
        "id": 14,
        "short_title": "🎵 Solar Plexus",
        "title": "Divine sound Solarplexuschakra and Spleenchakra from God",
        "description": (
            "Step into your power with confidence and clarity.\n"
            "Empowering frequencies for confidence, personal power, and clarity. Supports motivation, "
            "inner strength, and self-belief. A daily boost for your willpower and direction in life. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Solarplexuschakra-and-Spleenchakra-from-God.png",
        "audio": "songs/Divine sound Solarplexuschakra and Spleenchakra from God.mp3",
        "buy_url": "https://buy.stripe.com/8x2fZg2Vf64v0uN5K9cfK0e",
        "buy_url_sek": "https://buy.stripe.com/8x2fZg2Vf64v0uN5K9cfK0e"
    },
    {
        "id": 15,
        "short_title": "🎵 Testosterone",
        "title": "Divine sound Testosteron from God",
        "description": (
            "Build strength, focus, and powerful inner energy.\n"
            "Strong, stabilizing vibrations to support masculine energy, strength, and vitality. "
            "Helps balance hormones, increase focus, and build inner power and confidence. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 1600,
        "cover": "covers/Divine-sound-Testosteron-from-God.png",
        "audio": "songs/Divine sound Testosteron from God.mp3",
        "buy_url": "https://buy.stripe.com/6oUeVc2Vf50r5P78WlcfK0f",
        "buy_url_sek": "https://buy.stripe.com/6oUeVc2Vf50r5P78WlcfK0f"
    },
    {
        "id": 16,
        "short_title": "🎵 Vitamins",
        "title": "Divine sound Vitamins from God",
        "description": (
            "Nourish your body with essential energy and divine vitality.\n"
            "Energizing sound frequencies designed to support your body with essential nourishment "
            "and vitality. Helps restore balance, strengthen overall well-being, and awaken natural "
            "energy from within. A daily sound ritual to feel refreshed, supported, and aligned. "
            "Listen daily for best results."
        ),
        "price": "$16",
        "price_amount": 100,
        "cover": "covers/Divine-sound-Vitamins-from-God.png",
        "audio": "songs/Divine sound Vitamins from God.mp3",
        "buy_url": "https://buy.stripe.com/aFaaEW9jD50rdhz7ShcfK0h",
        "buy_url_sek": "https://buy.stripe.com/8x228qanHfF5cdv4G5cfK0g"
    },
]


def _tracks_data_dir() -> Path:
    return Path(__file__).resolve().parent


def _read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _build_merged_catalog() -> list[dict]:
    """
    Собираем итоговый список: встроенные треки минус удалённые, + правки полей, + треки из tracks_extra.json.
    Порядок элементов в _BUILTIN_TRACKS задаёт порядок кнопок каталога в Telegram-боте.
    Вызывается при старте и после админских изменений (reload_track_catalog).
    """
    deleted_raw = _read_json(_tracks_data_dir() / "tracks_deleted.json", [])
    deleted: set[int] = set()
    if isinstance(deleted_raw, list):
        for x in deleted_raw:
            try:
                deleted.add(int(x))
            except (TypeError, ValueError):
                continue
    overrides = _read_json(_tracks_data_dir() / "track_overrides.json", {})
    if not isinstance(overrides, dict):
        overrides = {}
    extras = _read_json(_tracks_data_dir() / "tracks_extra.json", [])
    if not isinstance(extras, list):
        extras = []

    out: list[dict] = []
    for t in _BUILTIN_TRACKS:
        tid = int(t["id"])
        if tid in deleted:
            continue
        merged = deepcopy(t)
        ov = overrides.get(str(tid))
        if isinstance(ov, dict):
            merged.update(ov)
        gid = _BUILTIN_GOOGLE_DRIVE_IDS.get(tid)
        if gid and not str(merged.get("google_drive_file_id") or "").strip():
            merged["google_drive_file_id"] = gid
        out.append(merged)
    for raw in extras:
        if isinstance(raw, dict) and "id" in raw:
            out.append(deepcopy(raw))

    # TEST_MODE: один тестовый линк вместо buy.stripe.com без test_ (fallback на сайте, если checkout не сработал).
    test_link = _test_payment_link_for_all_tracks()
    if test_link:
        for t in out:
            if str(t.get("price", "")).strip().upper() == "FREE":
                continue
            try:
                if int(t.get("price_amount") or -1) == 0:
                    continue
            except (TypeError, ValueError):
                pass
            t["buy_url"] = test_link
            t["buy_url_sek"] = test_link
    return out


# Единый список для бота и get_track; перезагрузка — reload_track_catalog().
TRACKS: list[dict] = _build_merged_catalog()


def reload_track_catalog() -> None:
    """Перечитать JSON-слои и обновить TRACKS на месте (те же ссылки на список для импортировавших модуль)."""
    TRACKS.clear()
    TRACKS.extend(_build_merged_catalog())


def get_track(track_id: int) -> dict | None:
    """Return one track dict by numeric id, or None if missing."""
    for t in TRACKS:
        if t["id"] == track_id:
            return t
    return None
