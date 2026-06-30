#!/usr/bin/env python3
"""
Broken Arrow — build manifest extractor.

Writes output/manifest.json: provenance for a dump, independent of the decrypted
table data. Every field here comes from the AssetRipper export's ProjectSettings
or a hash of the encrypted asset — no AES key and no decryption required, so it
runs (and stays meaningful) on its own:

    game_version  : ProjectSettings/ProjectSettings.asset   (bundleVersion)
    unity_version : ProjectSettings/ProjectVersion.txt      (m_EditorVersion)
    data_level    : Assets/Resources/DataBaseCompiled.asset (Level:)
    source_sha256 : SHA-256 of that same .asset  -> the definitive "did the
                    data actually change this patch?" signal, timestamp-free.

Usage:
    python tools/extract_manifest.py
    python tools/extract_manifest.py --root ExportedProject --out output
    python tools/extract_manifest.py --game-version 1.1.0.2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = "ExportedProject"
DEFAULT_OUT = "output"

# Paths relative to the AssetRipper export root.
PROJECT_SETTINGS_REL = "ProjectSettings/ProjectSettings.asset"
PROJECT_VERSION_REL = "ProjectSettings/ProjectVersion.txt"
ASSET_REL = "Assets/Resources/DataBaseCompiled.asset"


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def match_first(path: Path, pattern: str) -> str | None:
    """First regex group-1 match in a text file, or None if missing/unmatched."""
    if not path.is_file():
        return None
    m = re.search(pattern, path.read_text(encoding="utf-8", errors="replace"), re.M)
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Write Broken Arrow build manifest.json.")
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help="AssetRipper export root (holds ProjectSettings/ and Assets/)")
    ap.add_argument("--asset", default=None,
                    help=f"override path to DataBaseCompiled.asset (default: <root>/{ASSET_REL})")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--game-version", default=None,
                    help="override game version (default: read bundleVersion from ProjectSettings)")
    args = ap.parse_args()

    root = Path(args.root)
    asset_path = Path(args.asset) if args.asset else root / ASSET_REL

    game_version = args.game_version or match_first(
        root / PROJECT_SETTINGS_REL, r"^  bundleVersion: (.+?)\s*$")
    if game_version is None:
        warn(f"no bundleVersion in {root / PROJECT_SETTINGS_REL}; game_version = null")

    unity_version = match_first(root / PROJECT_VERSION_REL, r"^m_EditorVersion: (.+?)\s*$")
    if unity_version is None:
        warn(f"no m_EditorVersion in {root / PROJECT_VERSION_REL}; unity_version = null")

    data_level = source_sha256 = None
    if asset_path.is_file():
        level = match_first(asset_path, r"^  Level: (-?\d+)\s*$")
        data_level = int(level) if level is not None else None
        source_sha256 = sha256_file(asset_path)
    else:
        warn(f"asset not found: {asset_path}; data_level/source_sha256 = null")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "game_version": game_version,
        "data_level": data_level,
        "unity_version": unity_version,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_asset": str(asset_path),
        "source_sha256": source_sha256,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    short = source_sha256[:12] + "…" if source_sha256 else "n/a"
    print(f"Wrote {out_dir / 'manifest.json'} (game {game_version}, sha256 {short})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
