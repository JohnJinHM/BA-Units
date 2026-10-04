#!/usr/bin/env python3
"""Check a complete dump, its joins, combined JSON and build manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from table_schema import FIELD_TO_TABLE

REFERENCES = {
    "Units": {"CountryId": "Countries"},
    "UnitArmors": {"UnitId": "Units", "ArmorId": "Armors"},
    "UnitPropulsions": {"UnitId": "Units", "MobilityId": "Mobility"},
    "SensorUnits": {"UnitId": "Units", "SensorId": "Sensors"},
    "UnitAbilities": {"UnitId": "Units", "AbilityId": "Abilities"},
    "Turrets": {"ParentTurretId": "Turrets"},
    "TurretUnits": {"UnitId": "Units", "TurretId": "Turrets"},
    "TurretWeapons": {"TurretId": "Turrets", "WeaponId": "Weapons"},
    "WeaponAmmunitions": {"UnitId": "Units", "WeaponId": "Weapons", "AmmunitionId": "Ammunitions"},
    "SquadMembers": {"UnitId": "Units", "PrimaryWeaponId": "Weapons", "SpecialWeaponId": "Weapons"},
    "SquadWeapons": {"UnitId": "Units", "WeaponId": "Weapons"},
    "Modifications": {"UnitId": "Units"},
    "Mobility": {"FlyPresetId": "PlaneFlyPresets"},
    "Options": {
        "ModificationId": "Modifications", "ReplaceUnitId": "Units",
        "ArmorId": "Armors", "MobilityId": "Mobility",
        "MainSensorId": "Sensors", "ExtraSensorId": "Sensors",
        **{f"Ability{i}Id": "Abilities" for i in range(1, 4)},
        **{f"Turret{i}Id": "Turrets" for i in range(21)},
    },
    "Specializations": {"CountryId": "Countries"},
    "SpecializationAvailabilities": {"UnitId": "Units", "SpecializationId": "Specializations"},
    "TransportAvailabilities": {"UnitId": "Units", "SpecializationAvailabilityId": "SpecializationAvailabilities"},
}


def validate(out: Path, asset: Path | None = None) -> tuple[int, int]:
    names = set(FIELD_TO_TABLE.values())
    files = {p.stem: p for p in (out / "tables").glob("*.json")}
    if files.keys() != names:
        raise ValueError(f"table mismatch: missing {names - files.keys()}, extra {files.keys() - names}")
    tables = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in files.items()}
    ids = {}
    for name, rows in tables.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"{name}: expected an array of rows")
        row_ids = [row.get("Id") for row in rows]
        if any(type(row_id) is not int for row_id in row_ids) or len(set(row_ids)) != len(row_ids):
            raise ValueError(f"{name}: invalid or duplicate IDs")
        ids[name] = set(row_ids)
    for name, refs in REFERENCES.items():
        for row in tables[name]:
            for column, target in refs.items():
                value = row[column]
                # 0 and -1 are the game's unset/clear-override sentinels.
                if value is not None and value > 0 and value not in ids[target]:
                    raise ValueError(f"{name}[{row['Id']}].{column}={value} is missing from {target}")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    counts = {name: len(rows) for name, rows in tables.items()}
    if manifest.get("row_counts") != counts or manifest.get("tables") != len(counts) or manifest.get("total_rows") != sum(counts.values()):
        raise ValueError("manifest row counts do not match the tables")
    if asset and manifest.get("source_sha256") != hashlib.sha256(asset.read_bytes()).hexdigest():
        raise ValueError("manifest source hash does not match the exported asset")
    combined = out / "database.json"
    if combined.is_file() and json.loads(combined.read_text(encoding="utf-8")) != tables:
        raise ValueError("database.json does not match the per-table files")
    for path in (out / "localization").glob("*.json"):
        strings = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(strings, dict) or any(value is not None and not isinstance(value, str) for value in strings.values()):
            raise ValueError(f"{path.name}: invalid localization map")
    return len(counts), sum(counts.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument("--asset", type=Path)
    args = parser.parse_args()
    try:
        tables, rows = validate(args.out, args.asset)
    except (ValueError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Validated {tables} tables, {rows} rows, joins and manifest in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
