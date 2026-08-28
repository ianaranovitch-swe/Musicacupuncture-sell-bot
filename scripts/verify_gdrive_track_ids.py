#!/usr/bin/env python3
"""
Проверка google_drive_file_id для всех треков и (опционально) список MP3 в папке Drive.

Запуск (локально, нужен GOOGLE_SERVICE_ACCOUNT_JSON в .env или env):
  python scripts/verify_gdrive_track_ids.py
  python scripts/verify_gdrive_track_ids.py --folder 1IIswNwk_-OLbnSb3H57b61K9WRFvitvL

После копирования MP3 в другую папку Drive у файлов новые ID — обновите tracks.py
или временно GDRIVE_IDS_JSON на Railway (ключ = stem без .mp3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tracks
from music_sales.google_drive_delivery import (
    drive_file_metadata,
    get_drive_service,
    service_account_client_email,
)


def _list_folder_mp3s(folder_id: str) -> list[dict[str, str]]:
    service = get_drive_service()
    if not service:
        raise RuntimeError("Drive service unavailable — check GOOGLE_SERVICE_ACCOUNT_JSON")

    q = f"'{folder_id}' in parents and mimeType='audio/mpeg' and trashed=false"
    files: list[dict[str, str]] = []
    page_token: str | None = None
    while True:
        resp = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(id,name,size)",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=100,
            )
            .execute()
        )
        for item in resp.get("files") or []:
            name = str(item.get("name") or "")
            fid = str(item.get("id") or "")
            if name.lower().endswith(".mp3") and fid:
                files.append({"id": fid, "name": name, "stem": Path(name).stem})
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return sorted(files, key=lambda x: x["name"].lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Drive file IDs for website MP3 delivery")
    parser.add_argument(
        "--folder",
        help="Google Drive folder ID — list MP3s and print stem→id JSON for tracks.py / GDRIVE_IDS_JSON",
    )
    args = parser.parse_args()

    tracks.reload_track_catalog()
    failed: list[str] = []
    print(f"Service account: {service_account_client_email() or '(unknown)'}")
    print("--- builtin IDs ---")
    for tid, expected in sorted(tracks._BUILTIN_GOOGLE_DRIVE_IDS.items()):
        row = next((t for t in tracks.TRACKS if int(t["id"]) == tid), None)
        stem = Path(str((row or {}).get("audio") or "")).stem or "?"
        meta, err = drive_file_metadata(expected)
        if meta:
            name = meta.get("name") or stem
            size_raw = meta.get("size")
            size = size_raw if size_raw is not None else "?"
            print(f"OK  id={tid:2d} drive={expected}  {name} ({size} B)")
        else:
            print(f"FAIL id={tid:2d} drive={expected}  stem={stem}  err={err}")
            failed.append(stem)

    if args.folder:
        print(f"\n--- MP3 in folder {args.folder} ---")
        try:
            mp3s = _list_folder_mp3s(args.folder.strip())
        except Exception as e:
            print(f"Could not list folder: {e}")
            return 2
        mapping = {item["stem"]: item["id"] for item in mp3s}
        for item in mp3s:
            print(f"  {item['name']}  ->  {item['id']}")
        print("\n--- GDRIVE_IDS_JSON snippet (stems with + as in filename) ---")
        print(json.dumps(mapping, indent=2, ensure_ascii=False))

    if failed:
        print(f"\n{len(failed)} Drive ID(s) failed. Update tracks.py after copying MP3s to a new folder.")
        return 1
    print("\nAll builtin Drive IDs reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
