"""
Подготовка фото футляра для Telegram: квадрат с фоном как в Mini App (contain).

Обложка «диск» шлётся из bot_handlers как исходный PNG с альфой — без обработки здесь.
Без Pillow возвращаем None — тогда bot_handlers отправляет файл как есть.
"""

from __future__ import annotations

import io
from pathlib import Path

# Как фон под обложкой в Mini App (.card-img-wrap)
_CASE_BG = (42, 15, 74, 255)


def render_free_track_cover_for_telegram(
    path: Path,
    style: str = "case_square",
    *,
    output_size: int = 1024,
) -> bytes | None:
    """Собрать PNG в памяти: картинка целиком в квадрате (для front/back футляра)."""
    if style != "case_square":
        return None
    try:
        from PIL import Image
    except ImportError:
        return None

    if not path.is_file():
        return None

    try:
        src = Image.open(path)
        src.load()
    except OSError:
        return None

    resample = getattr(Image, "Resampling", Image).LANCZOS
    out = _to_square_case(src.convert("RGBA"), output_size, resample)

    buf = io.BytesIO()
    try:
        out.save(buf, format="PNG", optimize=True)
    except OSError:
        return None
    return buf.getvalue()


def _to_square_case(src, size: int, resample):
    from PIL import Image

    w, h = src.size
    scale = min(size / w, size / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    src = src.resize((nw, nh), resample)

    canvas = Image.new("RGBA", (size, size), _CASE_BG)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas.paste(src, (ox, oy), src)
    return canvas
