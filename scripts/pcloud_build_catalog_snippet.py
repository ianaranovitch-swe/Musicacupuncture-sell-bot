#!/usr/bin/env python3
"""
Собрать pcloud_fileid для MP3 из папки pCloud и вывести JSON для songs/catalog.json.

Зачем: ключи в catalog.json — это точные имена файлов в папке songs/ (например «Divine sound ….mp3»).
В ответе listfolder у каждого файла есть fileid — его и подставляем.

Как пользоваться (локально, токен не коммитить):
  1) В .env: PCLOUD_AUTH_TOKEN=...  и при EU: PCLOUD_API_HOST=eapi.pcloud.com
  2) Залей все 18 MP3 в одну папку в pCloud (или знай folderid этой папки).
  3) Из корня репозитория:
       python scripts/pcloud_build_catalog_snippet.py --folder-id 12345678
     или по пути в облаке:
       python scripts/pcloud_build_catalog_snippet.py --path "/Music/songs"
  4) Скопируй выведенный JSON в songs/catalog.json (или используй --merge).

  Обновить только поле pcloud_fileid, не трогая остальное:
       python scripts/pcloud_build_catalog_snippet.py --folder-id 12345678 --merge songs/catalog.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import requests


def _api_host() -> str:
    raw = (os.environ.get("PCLOUD_API_HOST") or "api.pcloud.com").strip().lower()
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
    return (raw.split("/")[0] or "api.pcloud.com").strip()


def _listfolder(auth: str, *, folder_id: int | None, path: str | None) -> dict[str, Any]:
    host = _api_host()
    url = f"https://{host}/listfolder"
    params: dict[str, Any] = {"auth": auth}
    if path:
        params["path"] = path
    else:
        params["folderid"] = int(folder_id if folder_id is not None else 0)
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if int(data.get("result", -1)) != 0:
        raise SystemExit(f"pCloud listfolder error: result={data.get('result')} {data!r}")
    return data


def _mp3_entries_from_listfolder(data: dict[str, Any]) -> list[tuple[str, int]]:
    """Пары (имя_файла.mp3, fileid) из metadata.contents (без рекурсии)."""
    meta = data.get("metadata") or {}
    contents = meta.get("contents") or []
    out: list[tuple[str, int]] = []
    for item in contents:
        if not isinstance(item, dict):
            continue
        if item.get("isfolder"):
            continue
        name = str(item.get("name") or "")
        if not name.lower().endswith(".mp3"):
            continue
        try:
            fid = int(item["fileid"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append((name, fid))
    return sorted(out, key=lambda x: x[0].lower())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build catalog.json snippet with pcloud_fileid from pCloud listfolder (non-recursive)."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--folder-id", type=int, help="Numeric folderid of the pCloud folder (see pCloud API / web).")
    g.add_argument("--path", type=str, help='Cloud path to folder, e.g. "/Music/songs".')
    ap.add_argument(
        "--merge",
        type=str,
        metavar="CATALOG_JSON",
        help="Update existing JSON: set pcloud_fileid by exact filename key.",
    )
    args = ap.parse_args()

    auth = (os.environ.get("PCLOUD_AUTH_TOKEN") or "").strip()
    if not auth:
        print("Error: set PCLOUD_AUTH_TOKEN in environment or .env", file=sys.stderr)
        return 1

    data = _listfolder(auth, folder_id=args.folder_id, path=args.path)
    pairs = _mp3_entries_from_listfolder(data)

    if not pairs:
        print("No .mp3 files in this folder (check folderid/path).", file=sys.stderr)
        return 2

    print(f"MP3 files found: {len(pairs)} (API host: {_api_host()})")
    print("--- table: fileid <tab> filename ---")
    for name, fid in pairs:
        print(f"{fid}\t{name}")

    snippet: dict[str, dict[str, Any]] = {}
    for name, fid in pairs:
        snippet[name] = {"pcloud_fileid": str(fid)}

    print("\n--- snippet for songs/catalog.json (merge with \"name\" if needed) ---")
    print(json.dumps(snippet, ensure_ascii=False, indent=2))

    if args.merge:
        p = Path(args.merge)
        if not p.is_file():
            print(f"File not found: {p}", file=sys.stderr)
            return 3
        existing = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            print("catalog.json must be a single JSON object { ... }", file=sys.stderr)
            return 4
        for fname, body in snippet.items():
            if fname not in existing:
                existing[fname] = {
                    "name": Path(fname).stem.replace("_", " ").strip() or fname,
                    "pcloud_fileid": body["pcloud_fileid"],
                }
            else:
                if not isinstance(existing[fname], dict):
                    existing[fname] = {}
                existing[fname]["pcloud_fileid"] = body["pcloud_fileid"]
        p.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nUpdated file: {p.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
