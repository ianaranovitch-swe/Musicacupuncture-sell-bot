"""
Upload each catalog WAV from songs/ via the Bot API, collect Telegram file_id values.

Requires in .env:
  BOT_TOKEN
  UPLOAD_CHAT_ID or OWNER_TELEGRAM_ID — numeric Telegram user id where the bot sends files
    (open @userinfobot, copy id; bot must be able to message that chat — start the bot first).

Run:  python upload_songs.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from tracks import TRACKS

# Бесплатный бонус: грузим тоже, чтобы file_id оказался в file_ids.json / FILE_IDS_JSON.
_FREE_BONUS_AUDIO = "songs/Divine sound Super Feng Shui from God.mp3"

load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "file_ids.json"


def _chat_id() -> int:
    for key in ("UPLOAD_CHAT_ID", "OWNER_TELEGRAM_ID"):
        raw = os.getenv(key, "").strip()
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


async def _run() -> None:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN in .env.")
    chat_id = _chat_id()

    results: dict[str, str] = _load_existing()
    # Large WAV uploads: media_write_timeout caps file uploads (default 20s is too low).
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=600.0,
        write_timeout=600.0,
        pool_timeout=30.0,
        media_write_timeout=600.0,
    )
    bot = Bot(token, request=request)

    async with bot:
        for track in TRACKS:
            rel = track["audio"]
            path = ROOT / rel
            key = Path(rel).stem

            if not path.is_file():
                print(f"Missing file (skipped): {rel}")
                continue

            print(f"Uploading: {path.name}...", end=" ", flush=True)
            try:
                with path.open("rb") as fh:
                    msg = await bot.send_document(
                        chat_id=chat_id,
                        document=fh,
                        filename=path.name,
                    )
            except TelegramError as e:
                print(f"Error: {e}")
                continue
            except OSError as e:
                print(f"Error reading file: {e}")
                continue

            doc = msg.document
            if doc is None:
                print("Error: no document in Telegram response.")
                continue

            fid = doc.file_id
            results[key] = fid
            OUTPUT.write_text(
                json.dumps(results, ensure_ascii=False, indent=4) + "\n",
                encoding="utf-8",
            )
            print(f"Done! file_id: {fid}")

        # Отдельно грузим бесплатный бонус, который не входит в tracks.py.
        bonus_path = ROOT / _FREE_BONUS_AUDIO
        bonus_key = Path(_FREE_BONUS_AUDIO).stem
        if bonus_path.is_file() and bonus_key not in results:
            print(f"Uploading bonus: {bonus_path.name}...", end=" ", flush=True)
            try:
                with bonus_path.open("rb") as fh:
                    msg = await bot.send_document(
                        chat_id=chat_id,
                        document=fh,
                        filename=bonus_path.name,
                    )
            except TelegramError as e:
                print(f"Error: {e}")
            except OSError as e:
                print(f"Error reading file: {e}")
            else:
                doc = msg.document
                if doc is None:
                    print("Error: no document in Telegram response.")
                else:
                    fid = doc.file_id
                    results[bonus_key] = fid
                    OUTPUT.write_text(
                        json.dumps(results, ensure_ascii=False, indent=4) + "\n",
                        encoding="utf-8",
                    )
                    print(f"Done! file_id: {fid}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
