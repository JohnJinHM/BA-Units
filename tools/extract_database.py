#!/usr/bin/env python3
"""
Broken Arrow — unit database extractor.

Decrypts the 24 encrypted tables stored inside the Unity ScriptableObject
`DataBaseCompiled.asset` and writes them out as plain JSON, ready to feed the
card-reconstruction tool / import into a local database.

How the data is stored (recovered from GameAssembly.dll, see docs/EXTRACTION.md):

    DataBaseCompiled (ScriptableObject)
      .Units, .WeaponsJson, .AmmunitionsJson, ...   (24 string fields)

    each field = Base64( marker(8) || IV(16) || AES-256-CBC( PKCS7( UTF8(json) ) ) )
        marker = b"fhk3s0g3"
        key    = UTF8("09234237536700238099172758697347")   # 32 bytes => AES-256
        IV     = the 16 bytes that follow the marker (per-blob, random)

The decrypt logic lives in BrokenArrow.Core.Security.EncryptedFileManager.
If the game updates and the key/marker change, re-recover them with
`tools/recover_key.py` (no guessing required) and pass --key / --marker here.

Build provenance (game version, source hash, …) is written separately by
tools/extract_manifest.py, which reads it from ProjectSettings without needing
the decryption key.

Usage:
    python tools/extract_database.py
    python tools/extract_database.py --asset path/to/DataBaseCompiled.asset --out output
    python tools/extract_database.py --key 09234... --marker fhk3s0g3
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    sys.exit("Missing dependency. Run:  pip install -r requirements.txt")

# --- defaults for the current game build -----------------------------------
DEFAULT_KEY = "09234237536700238099172758697347"   # AES-256 key (UTF-8 bytes)
DEFAULT_MARKER = "fhk3s0g3"
DEFAULT_ASSET = "ExportedProject/Assets/Resources/DataBaseCompiled.asset"
DEFAULT_OUT = "output"

# ScriptableObject string field  ->  output table name.
# Every field below holds an encrypted JSON array (see module docstring).
FIELD_TO_TABLE = {
    "Units": "Units",
    "AbilitiesJson": "Abilities",
    "UnitAbilitiesJson": "UnitAbilities",
    "AmmunitionsJson": "Ammunitions",
    "ArmorsJson": "Armors",
    "MobilityJson": "Mobility",
    "FlyPresetsJson": "PlaneFlyPresets",
    "UnitPropulsionsJson": "UnitPropulsions",
    "CountriesJson": "Countries",
    "TurretsJson": "Turrets",
    "TurretUnitsJson": "TurretUnits",
    "WeaponsJson": "Weapons",
    "TurretWeaponsJson": "TurretWeapons",
    "WeaponAmmunitionsJson": "WeaponAmmunitions",
    "SensorUnitsJson": "SensorUnits",
    "SensorsJson": "Sensors",
    "SquadMembersJson": "SquadMembers",
    "SquadWeaponsJson": "SquadWeapons",
    "ModificationsJson": "Modifications",
    "OptionsJson": "Options",
    "UnitArmorsJson": "UnitArmors",
    "SpecializationAvailabilitiesJson": "SpecializationAvailabilities",
    "SpecializationsJson": "Specializations",
    "TransportAvailabilitiesJson": "TransportAvailabilities",
}


def read_asset_fields(asset_path: Path) -> dict[str, str]:
    """Pull the raw Base64 string of each known field out of the YAML asset.

    The asset is a Unity YAML file; each field is a single long line of the
    form `  FieldName: <base64>`. We do not need a YAML parser for this.
    """
    text = asset_path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for field in FIELD_TO_TABLE:
        m = re.search(r"^  " + re.escape(field) + r": (.*)$", text, re.M)
        if not m:
            print(f"  ! field not found in asset: {field}", file=sys.stderr)
            continue
        value = m.group(1).strip()
        if value and value != "''":
            out[field] = value
    return out


def decrypt_blob(b64: str, key: bytes, marker: bytes) -> str:
    """Base64 -> strip marker -> AES-256-CBC decrypt -> UTF-8 JSON text."""
    raw = base64.b64decode(b64)
    if not raw.startswith(marker):
        raise ValueError(
            f"blob does not start with marker {marker!r}; "
            f"the key/marker may have changed (re-run tools/recover_key.py)"
        )
    body = raw[len(marker):]
    iv, ciphertext = body[:16], body[16:]
    plaintext = AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)
    plaintext = unpad(plaintext, AES.block_size)
    return plaintext.decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract Broken Arrow unit DB to JSON.")
    ap.add_argument("--asset", default=DEFAULT_ASSET, help="path to DataBaseCompiled.asset")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--key", default=DEFAULT_KEY, help="AES key (UTF-8 text)")
    ap.add_argument("--marker", default=DEFAULT_MARKER, help="blob magic marker")
    ap.add_argument("--combined", action="store_true",
                    help="also write a single database.json with every table")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (0 = compact)")
    args = ap.parse_args()

    asset_path = Path(args.asset)
    if not asset_path.is_file():
        return _fail(f"asset not found: {asset_path}")

    key = args.key.encode("utf-8")
    if len(key) not in (16, 24, 32):
        return _fail(f"key must be 16/24/32 bytes for AES, got {len(key)}")
    marker = args.marker.encode("utf-8")

    out_dir = Path(args.out)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    indent = args.indent or None

    fields = read_asset_fields(asset_path)
    print(f"Found {len(fields)} encrypted fields in {asset_path.name}")

    combined: dict[str, list] = {}
    total_rows = 0
    for field, b64 in fields.items():
        table = FIELD_TO_TABLE[field]
        try:
            rows = json.loads(decrypt_blob(b64, key, marker))
        except Exception as exc:  # noqa: BLE001 - report and continue per table
            print(f"  ! {table}: {exc}", file=sys.stderr)
            continue
        (tables_dir / f"{table}.json").write_text(
            json.dumps(rows, indent=indent, ensure_ascii=False), encoding="utf-8"
        )
        combined[table] = rows
        n = len(rows) if isinstance(rows, list) else 1
        total_rows += n
        print(f"  + {table:<32} {n:>5} rows")

    if args.combined:
        (out_dir / "database.json").write_text(
            json.dumps(combined, indent=indent, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Wrote combined database.json ({len(combined)} tables)")

    print(f"Done. {len(combined)} tables, {total_rows} rows -> {tables_dir}")
    return 0


def _fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
