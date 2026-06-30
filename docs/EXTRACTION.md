# Extraction — how the unit data is stored and decrypted

This documents the full reverse-engineering result so the pipeline can be
maintained without re-discovering it.

## 1. Where the data lives

The entire unit database ships inside one Unity ScriptableObject:

```
ExportedProject/Assets/Resources/DataBaseCompiled.asset
```

Class: `BrokenArrow.Shared.Ecs.DataBaseCompiled` (a `ScriptableObject`). It has
**24 string fields**, each an encrypted JSON array for one relational table:

```
Units, AbilitiesJson, UnitAbilitiesJson, AmmunitionsJson, ArmorsJson,
MobilityJson, FlyPresetsJson, UnitPropulsionsJson, CountriesJson, TurretsJson,
TurretUnitsJson, WeaponsJson, TurretWeaponsJson, WeaponAmmunitionsJson,
SensorUnitsJson, SensorsJson, SquadMembersJson, SquadWeaponsJson,
ModificationsJson, OptionsJson, UnitArmorsJson,
SpecializationAvailabilitiesJson, SpecializationsJson, TransportAvailabilitiesJson
```

(There is also an `int Level` field — a content/version marker, value `2` in the
analysed build. It is not part of the data.)

The original authoring source is a SQLite database (`DataBaseSourceData` uses
`SQLite4Unity3d`), but the *shipped* form is the encrypted blobs above. No
plaintext DB or JSON is shipped, hence the decryption step.

## 2. The blob format

Each field is processed by `DataBaseCompiled.DeserializeCrypt<T>(string)`, which
is simply:

```
FromBase64String  ->  EncryptedFileManager.DecryptAllBytes  ->  UTF8.GetString  ->  JsonConvert.DeserializeObject<T>
```

`BrokenArrow.Core.Security.EncryptedFileManager` defines the byte layout. After
Base64-decoding, every blob is:

```
+----------------+------------------+-----------------------------------+
| marker (8 B)   | IV (16 B)        | AES-256-CBC ciphertext (PKCS7)    |
| "fhk3s0g3"     | random per blob  | PKCS7( UTF8( json ) )             |
+----------------+------------------+-----------------------------------+
```

- **Cipher:** AES-256-CBC, PKCS7 padding.
- **Key:** UTF-8 bytes of the literal `09234237536700238099172758697347`
  (32 ASCII chars → 32-byte / 256-bit key).
- **Marker:** ASCII `fhk3s0g3`, used to detect "is this encrypted".
- **IV:** the 16 bytes immediately after the marker (generated per blob at
  encrypt time, so it differs for every field).
- **Ciphertext length** is always a multiple of 16 (e.g. Units: 273664 B = 17104
  blocks), confirming CBC + block padding.

Decrypting gives a UTF-8 JSON array, e.g. `Countries`:

```json
[{"Id":1,"Name":"Russia","UIName":"Russia","FlagFileName":"rus flag",
  "MaxPoints":10000,"Hidden":false,"ContentMembership":-1}, ...]
```

## 3. Reproducing the decrypt (`tools/extract_database.py`)

The script:
1. Reads each `FieldName: <base64>` line out of the YAML asset (no YAML parser
   needed — each value is a single line).
2. For each: Base64-decode → check/strip the 8-byte marker → split IV(16) +
   ciphertext → AES-256-CBC decrypt → PKCS7-unpad → `json.loads`.
3. Writes `output/tables/<Table>.json` (+ optional combined `database.json`).

Key + marker are CLI options (`--key`, `--marker`) defaulting to the values
above, so a key rotation needs no code change.

## 4. How the key was recovered (and how to redo it)

The key/marker are **not** in the Unity assets — they are baked into native
code. Recovery used [Il2CppDumper](https://github.com/Perfare/Il2CppDumper):

1. `Il2CppDumper.exe GameAssembly.dll il2cpp_data/Metadata/global-metadata.dat out/`
   → produces `dump.cs` (RVAs), `script.json` (address→name, address→string),
   and dummy DLLs. Metadata/IL2CPP version = **31**.
2. In `dump.cs`, `DeserializeCrypt<object>` (RVA `0x1151320`) tail-calls
   `Convert.FromBase64String`, `EncryptedFileManager.DecryptAllBytes`,
   `Encoding.UTF8`, `JsonConvert.DeserializeObject<object>` — that established
   the pipeline.
3. `EncryptedFileManager..cctor` (RVA `0x768230`) builds the key/marker via
   `Encoding.UTF8.GetBytes(<string literal>)`. Disassembling it (capstone) gives
   two RIP-relative literal loads; resolving those data slots against
   `script.json`'s `ScriptString` map yields the literal values:
   - `09234237536700238099172758697347` → `Key`
   - `fhk3s0g3` → `EncryptedMarker`

`tools/recover_key.py` automates step 3: give it `GameAssembly.dll` and the
Il2CppDumper `script.json` and it prints the key + marker.

## Updating after a patch

Most patches only change the **data**, not the encryption:

```bash
# 1. Re-export with AssetRipper, replace DataBaseCompiled.asset locally.
# 2. Just re-run:
python tools/extract_database.py --combined
```

If `extract_database.py` reports *"blob does not start with marker"*, the key
and/or marker were rotated. Re-recover them:

```bash
# 1. Run Il2CppDumper on the new GameAssembly.dll + global-metadata.dat
Il2CppDumper.exe GameAssembly.dll il2cpp_data/Metadata/global-metadata.dat il2cpp_out

# 2. Recover key + marker (no guessing)
python tools/recover_key.py --dll GameAssembly.dll --script il2cpp_out/script.json

# 3. Re-extract with the new values
python tools/extract_database.py --combined --key <KEY> --marker <MARKER>
```

If the *class* was renamed, update `CCTOR_NAME` in `recover_key.py` (search
`dump.cs` for `Encoding.UTF8.GetBytes` near an `EncryptedMarker`/`Key` field).

## Tooling notes

- `pip install -r requirements.txt` (pycryptodome for decrypt; capstone + pefile
  only for `recover_key.py`).
- Il2CppDumper net7/net8 builds run on a newer .NET via
  `DOTNET_ROLL_FORWARD=LatestMajor`. It waits on a keypress at the end — that's
  cosmetic; the output files are already written.
