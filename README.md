# BA-Units

Extract clean, readable JSON of **unit data from the game [Broken Arrow](https://store.steampowered.com/app/644960/Broken_Arrow/)**.

The game ships its unit database encrypted inside its assets. This project decrypts
it and turns it into plain JSON files you can read, diff, or build tools on top of —
plus the small Python pipeline that produces them, so the data can be refreshed after
every game update.

> 🇨🇳 [中文](README_CN.md)

---

## What you get

Everything useful lives in [`output/`](output/):

| File | What it is |
|------|------------|
| [`output/tables/<Table>.json`](output/tables/) | One file per game table — a JSON array of rows (units, weapons, armor, sensors, …). |
| [`output/database.json`](output/database.json) | Every table in a single file: `{ "TableName": [ rows… ] }`. |
| [`output/localization/<lang>.json`](output/localization/) | A flat `{ key: text }` map so you can turn the IDs in the tables into readable names. |

There are **24 tables** in total:

> Units, Abilities, UnitAbilities, Ammunitions, Armors, Mobility, PlaneFlyPresets,
> UnitPropulsions, Countries, Turrets, TurretUnits, Weapons, TurretWeapons,
> WeaponAmmunitions, SensorUnits, Sensors, SquadMembers, SquadWeapons, Modifications,
> Options, UnitArmors, SpecializationAvailabilities, Specializations,
> TransportAvailabilities

The field names match the game's own data model, so a row looks like this:

```json
{ "Id": 1, "Name": "Russia", "UIName": "Russia",
  "FlagFileName": "rus flag", "MaxPoints": 10000,
  "Hidden": false, "ContentMembership": -1 }
```

**Just want the data?** Grab the files in `output/` — you don't need to run anything.

---

## Regenerating the data yourself

If you want to refresh the data after a game patch, or verify how it was produced:

```bash
pip install -r requirements.txt

# 1. Decrypt the unit database into JSON
python tools/extract_database.py --combined

# 2. Build a localization lookup (English by default; --all for every language)
python tools/extract_localization.py
```

### Source files you need locally

These come from your own copy of the game and are **not** included in this repo:

| What | Where it comes from |
|------|---------------------|
| Encrypted unit DB | `ExportedProject/Assets/Resources/DataBaseCompiled.asset` |
| Localization text | `ExportedProject/Assets/TextAsset/keys.json` + `<lang>.json` |
| Native code (only for key recovery) | `GameAssembly.dll` + `il2cpp_data/Metadata/global-metadata.dat` |

You get the `ExportedProject/` assets by exporting the game with
[AssetRipper](https://github.com/AssetRipper/AssetRipper).

---

## How it works (short version)

The unit database is a single encrypted Unity asset. Each table is stored as:

```
Base64( "fhk3s0g3" + IV(16 bytes) + AES-256-CBC( the JSON ) )
```

The decryption key is baked into the game's native code, not the assets, so it was
recovered once with [Il2CppDumper](https://github.com/Perfare/Il2CppDumper). The
key and marker are passed as options to the script, so a key change after a patch
needs **no code change** — just new values.

The full extraction pipeline is in
[docs/EXTRACTION.md](docs/EXTRACTION.md).

---

## After a game update

Most patches only change the **data**, not the encryption:

```bash
# 1. Re-export assets with AssetRipper, replace DataBaseCompiled.asset.
# 2. Re-run the extractor:
python tools/extract_database.py --combined
```

If the extractor complains that a blob *"does not start with marker"*, the developers
rotated the encryption key. Recover the new key and re-run — the steps are in
[docs/EXTRACTION.md](docs/EXTRACTION.md#updating-after-a-patch).

---

## Project layout

```
tools/
  extract_database.py      Decrypt the 24 tables → output/tables/*.json
  extract_localization.py  Flatten keys.json + <lang>.json → { key: text } maps
  recover_key.py           Re-recover the AES key after a game update
docs/
  EXTRACTION.md            Full technical write-up of the format & decryption
output/                    The generated JSON (the product of this repo)
requirements.txt
```
