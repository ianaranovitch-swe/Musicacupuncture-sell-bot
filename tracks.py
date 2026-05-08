"""Catalog of 17 tracks: cover and audio share the same base filename (.png / .mp3).

Поле buy_url_sek — ссылка Stripe в шведских кронах для Mini App; пока дублирует buy_url, замените на реальные SEK-ссылки.
"""

from __future__ import annotations

TRACKS: list[dict] = [
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
        "cover": "covers/Divine sound Crownchakra-Browchakra-Throatchakra from God.png",
        "audio": "songs/Divine sound Crownchakra-Browchakra-Throatchakra from God.mp3",
        "buy_url": "https://buy.stripe.com/28E3cubrLcsT2CV5K9cfK00",
        "buy_url_sek": "https://buy.stripe.com/28E3cubrLcsT2CV5K9cfK00"
    },
    {
        "id": 17,
        "short_title": "🎁 Free Gift",
        "title": "Divine sound Super Feng Shui from God",
        "description": (
            "Your free divine gift for home harmony and positive energy flow.\n"
            "A special bonus track designed to support calmness, balance, and uplifting atmosphere. "
            "Listen daily for best results."
        ),
        "price": "FREE",
        "price_amount": 0,
        "cover": "covers/Divine sound Super Feng Shui from God.png",
        "audio": "songs/Divine sound Super Feng Shui from God.mp3",
        "buy_url": "",
        "buy_url_sek": ""
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
        "cover": "covers/Divine sound Estrogen from God.png",
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
        "cover": "covers/Divine sound Heart from God.png",
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
        "cover": "covers/Divine sound Heartchakra and Diaphragmchakra from God.png",
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
        "cover": "covers/Divine sound Immunedefence from God.png",
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
        "cover": "covers/Divine sound Kidney from God.png",
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
        "cover": "covers/Divine sound Liver from God.png",
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
        "cover": "covers/Divine sound Lungs from God.png",
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
        "cover": "covers/Divine sound Minerals from God.png",
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
        "cover": "covers/Divine sound NO Alcohol from God.png",
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
        "cover": "covers/Divine sound NO Smoking from God.png",
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
        "cover": "covers/Divine sound Rootchakra from God.png",
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
        "cover": "covers/Divine sound Sacralchakra and Navelchakra from God.png",
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
        "cover": "covers/Divine sound Solarplexuschakra and Spleenchakra from God.png",
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
        "cover": "covers/Divine sound Testosteron from God.png",
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
        "cover": "covers/Divine sound Vitamins from God.png",
        "audio": "songs/Divine sound Vitamins from God.mp3",
        "buy_url": "https://buy.stripe.com/aFaaEW9jD50rdhz7ShcfK0h",
        "buy_url_sek": "https://buy.stripe.com/8x228qanHfF5cdv4G5cfK0g"
    },
]


def get_track(track_id: int) -> dict | None:
    """Return one track dict by numeric id, or None if missing."""
    for t in TRACKS:
        if t["id"] == track_id:
            return t
    return None
