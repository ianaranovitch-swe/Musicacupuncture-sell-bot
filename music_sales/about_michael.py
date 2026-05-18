"""
Тексты «About Michael» для бота и статических страниц (английский UI).
Фото: assets/about-michael.png и assets/about-michael-2.png в корне репозитория.
"""

from __future__ import annotations

from pathlib import Path

# Относительно корня репозитория (рядом с miniapp.html).
ABOUT_MICHAEL_PHOTO_REL = "assets/about-michael.png"
ABOUT_MICHAEL_PHOTO_2_REL = "assets/about-michael-2.png"
ABOUT_MICHAEL_PHOTO_RELS: tuple[str, ...] = (ABOUT_MICHAEL_PHOTO_REL, ABOUT_MICHAEL_PHOTO_2_REL)


def existing_about_michael_photos(root: Path) -> list[Path]:
    """Список файлов портретов, которые реально лежат на диске (для Telegram и деплоя)."""
    out: list[Path] = []
    for rel in ABOUT_MICHAEL_PHOTO_RELS:
        p = root / rel
        if p.is_file():
            out.append(p)
    return out


# Полный текст для сообщения в Telegram и для <main> на about.html
ABOUT_MICHAEL_BODY = """About Michael

Michael B. Johnsson is educated in several fields of alternative medicine, including Chiropractic, Acupuncture, and Kinesiology. His education and professional training have taken place in England, Denmark, and Sweden.

Over many years, Michael further deepened his knowledge through studies and practical training under the supervision of masters and practitioners in China, Korea, and other parts of Asia. During his time in Asia, he discovered the ancient principles of Tibetan sound therapy — a system based on the harmonizing effects of sound, vibration, and frequency on the human body and mind.

Inspired by this ancient wisdom, Michael spent years developing and refining a modern therapeutic method that eventually became MusicAcupuncture® — a unique system that combines traditional energetic principles with modern sound technology.

Today, MusicAcupuncture® is used by people around the world seeking relaxation, balance, energetic harmony, and support for overall well-being.

Welcome to discover MusicAcupuncture®.

— Michael B. Johnsson
Founder & President of MusicAcupuncture®"""

# Короткая подпись к первому фото в альбоме (лимит Telegram caption ~1024 символа)
ABOUT_MICHAEL_PHOTO_CAPTION = (
    "Michael B. Johnsson — Founder & President of MusicAcupuncture®. "
    "Read the full biography in the message below."
)
