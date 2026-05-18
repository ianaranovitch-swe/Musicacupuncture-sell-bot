"""
Печатает TESTIMONIALS_JSON для Railway Variables (одна строка, с [ и ]).

Использование:
  python scripts/export_testimonials_json_env.py
  python scripts/export_testimonials_json_env.py --file testimonials.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Export testimonials as TESTIMONIALS_JSON one-liner")
    parser.add_argument(
        "--file",
        type=Path,
        default=root / "testimonials.json",
        help="Path to testimonials.json (default: repo root testimonials.json)",
    )
    args = parser.parse_args()
    path = args.file
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        print("JSON must be an array starting with [", file=sys.stderr)
        return 1
    one_line = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if not one_line.startswith("[") or not one_line.endswith("]"):
        print("Invalid array output", file=sys.stderr)
        return 1
    print(one_line)
    print(f"\n# chars: {len(one_line)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
