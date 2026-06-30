#!/usr/bin/env python3
"""
Broken Arrow — localization extractor.

The game stores localization as two *parallel* JSON arrays per language:

    keys.json : ["keys", "apply", "select", ...]      # the string IDs
    eng.json  : ["eng",  "Apply", "Select", ...]      # the matching text

Index N in `keys.json` is the key for index N in `<lang>.json`. This script
zips them into a flat {key: text} map. Some unit/ability fields in the database
reference these keys (e.g. descriptions), so the card tool can resolve display
text through the produced map.

Usage:
    python tools/extract_localization.py
    python tools/extract_localization.py --lang ger --out output
    python tools/extract_localization.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_TEXT_DIR = "ExportedProject/Assets/TextAsset"
DEFAULT_OUT = "output/localization"
LANGS = ["eng", "rus", "ger", "chi", "spa", "fre", "jap", "por", "ita", "kor", "pol", "tur", "ukr"]


def load_array(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_map(keys_path: Path, lang_path: Path) -> dict[str, str]:
    keys = load_array(keys_path)
    vals = load_array(lang_path)
    if len(keys) != len(vals):
        print(f"  ! length mismatch: {keys_path.name}={len(keys)} "
              f"{lang_path.name}={len(vals)} (zipping to shortest)", file=sys.stderr)
    # First element of each array is the language tag, not a real entry; the
    # parallel structure still lines up by index, so we keep index 0 too.
    return dict(zip(keys, vals))


def main() -> int:
    ap = argparse.ArgumentParser(description="Flatten Broken Arrow localization to {key:text}.")
    ap.add_argument("--text-dir", default=DEFAULT_TEXT_DIR, help="folder with keys.json + <lang>.json")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--lang", default="eng", help="language code (e.g. eng, ger, rus)")
    ap.add_argument("--all", action="store_true", help="export every available language")
    args = ap.parse_args()

    text_dir = Path(args.text_dir)
    keys_path = text_dir / "keys.json"
    if not keys_path.is_file():
        print(f"ERROR: keys.json not found in {text_dir}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    langs = LANGS if args.all else [args.lang]
    for lang in langs:
        lang_path = text_dir / f"{lang}.json"
        if not lang_path.is_file():
            print(f"  ! skipping {lang}: {lang_path} not found", file=sys.stderr)
            continue
        mapping = build_map(keys_path, lang_path)
        (out_dir / f"{lang}.json").write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  + {lang}: {len(mapping)} keys")

    print(f"Done -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
