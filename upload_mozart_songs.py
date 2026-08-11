"""
Загрузка 14 новых Mozart MP3 в Telegram → file_id в file_ids.json.

Работает так же, как upload_songs.py, но только для Mozart-треков
(они ещё могут отсутствовать в tracks.py).

Нужно в .env:
  BOT_TOKEN
  UPLOAD_CHAT_ID или OWNER_TELEGRAM_ID — твой числовой Telegram id
    (напиши боту /start заранее, иначе он не сможет прислать файл).

Запуск:
  python upload_mozart_songs.py

Повторный запуск: уже загруженные ключи пропускаются.
Принудительно перезалить: python upload_mozart_songs.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

load_dotenv()

ROOT = Path(__file__).resolve().parent
SONGS_DIR = ROOT / "songs"
OUTPUT = ROOT / "file_ids.json"

# Имена файлов как в songs/ (без пробелов). Ключ в JSON = stem без .mp3.
MOZART_MP3_FILES: tuple[str, ...] = (
    "Mozart+5-Element-MULTI.mp3",
    "Mozart+Chakra-Multi.mp3",
    "Mozart+Crown-Chakra-Third-Eye.mp3",
    "Mozart+Heart.mp3",
    "Mozart+HEART-CHAKRA-Thimus-gland.mp3",
    "Mozart+Immune-System+Stomach.mp3",
    "Mozart+KIDNEYS+URINARY-BLADDER.mp3",
    "Mozart+Liver+GALLBLADDER.mp3",
    "Mozart+Lungs-Large-Intestine.mp3",
    "Mozart+ROOT-Chakra+Suprarenal-glands.mp3",
    # На диске: …-Organs (мн. число); в списке раньше было Organ — используем факт с диска.
    "Mozart+Sacral-Chakra+Reproductive-Organs.mp3",
    "Mozart+Solarplexus-Chakra+Pancreas_and_Liver-Glands.mp3",
    "Super-Mozart+5-Element-MULTI.mp3",
    "Super-Mozart+Chakra-MULTI.mp3",
)


def _chat_id() -> int:
    for key in ("UPLOAD_CHAT_ID", "OWNER_TELEGRAM_ID"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        try:
            return int(raw)
        except ValueError as e:
            raise SystemExit(f"{key} must be a numeric Telegram user id.") from e
    raise SystemExit(
        "Set UPLOAD_CHAT_ID or OWNER_TELEGRAM_ID in .env — Telegram needs a chat to send files to."
    )


def _load_existing() -> dict[str, str]:
    if not OUTPUT.is_file():
        return {}
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _save(results: dict[str, str]) -> None:
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


async def _run(*, force: bool) -> None:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN in .env.")
    chat_id = _chat_id()

    results = _load_existing()
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=600.0,
        write_timeout=600.0,
        pool_timeout=30.0,
        media_write_timeout=600.0,
    )
    bot = Bot(token, request=request)

    ok = 0
    skipped = 0
    missing = 0
    failed = 0

    async with bot:
        for name in MOZART_MP3_FILES:
            path = SONGS_DIR / name
            key = path.stem

            if not path.is_file():
                print(f"Missing file (skipped): songs/{name}")
                missing += 1
                continue

            if key in results and not force:
                print(f"Already have file_id (skipped): {name}")
                skipped += 1
                continue

            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"Uploading: {name} ({size_mb:.1f} MB)...", end=" ", flush=True)
            try:
                with path.open("rb") as fh:
                    msg = await bot.send_document(
                        chat_id=chat_id,
                        document=fh,
                        filename=path.name,
                    )
            except TelegramError as e:
                print(f"Error: {e}")
                failed += 1
                continue
            except OSError as e:
                print(f"Error reading file: {e}")
                failed += 1
                continue

            doc = msg.document
            if doc is None:
                print("Error: no document in Telegram response.")
                failed += 1
                continue

            fid = doc.file_id
            results[key] = fid
            _save(results)
            print(f"Done! file_id: {fid}")
            ok += 1

    print()
    print(f"Saved: {OUTPUT}")
    print(f"Uploaded: {ok} | skipped: {skipped} | missing: {missing} | failed: {failed}")
    print()
    print("Next steps:")
    print("1) Open file_ids.json and copy the new Mozart+ / Super-Mozart+ keys.")
    print("2) Merge them into Railway Web + Worker variable FILE_IDS_JSON")
    print("   (keep all old keys; add the 14 new ones).")
    print("3) Later we add the 14 tracks to tracks.py + Stripe links + descriptions.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload 14 Mozart MP3s to Telegram.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-upload even if file_id already exists in file_ids.json",
    )
    args = parser.parse_args()
    asyncio.run(_run(force=bool(args.force)))


if __name__ == "__main__":
    main()
