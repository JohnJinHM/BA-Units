#!/usr/bin/env python3
"""
Broken Arrow — AES key / marker recovery (for game updates).

The encryption key and marker are not stored in the Unity assets; they are
baked into native code. They live in the static constructor of
`BrokenArrow.Core.Security.EncryptedFileManager`, which does effectively:

    Key            = Encoding.UTF8.GetBytes("09234237536700238099172758697347")
    EncryptedMarker = Encoding.UTF8.GetBytes("fhk3s0g3")

This script recovers both *without guessing*, so the pipeline keeps working
after a patch even if the developers rotate the key.

Pipeline (one-time per game version):
  1. Run Il2CppDumper on the shipped binaries to produce `script.json`:
       Il2CppDumper.exe GameAssembly.dll global-metadata.dat <out>
     (download from https://github.com/Perfare/Il2CppDumper/releases)
  2. Point this script at GameAssembly.dll and that script.json:
       python tools/recover_key.py --dll GameAssembly.dll --script <out>/script.json

It finds EncryptedFileManager..cctor, disassembles it, follows the two
string-literal loads, and resolves them via Il2CppDumper's ScriptString map.

Output: prints the key + marker and (optionally) writes key.json you can feed
to extract_database.py via --key / --marker.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import pefile
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86 import X86_OP_MEM, X86_REG_RIP
except ImportError:
    sys.exit("Missing deps. Run:  pip install capstone pefile")

CCTOR_NAME = "BrokenArrow.Core.Security.EncryptedFileManager$$.cctor"


def find_method_rva(script: dict, name: str) -> int | None:
    for m in script.get("ScriptMethod", []):
        if m.get("Name") == name:
            return m["Address"]  # RVA
    return None


def collect_literal_slots(dll_path: Path, method_rva: int, max_bytes: int = 0x600) -> list[int]:
    """Disassemble the method and return the RVA of every rip-relative data
    slot it loads (the `mov reg, [rip+disp]` operands), in encounter order.

    String-literal references compile to a load from a fixed data slot; the
    slot RVA is what Il2CppDumper records in ScriptString.
    """
    pe = pefile.PE(str(dll_path), fast_load=True)
    file_off = pe.get_offset_from_rva(method_rva)
    code = pe.__data__[file_off:file_off + max_bytes]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    slots: list[int] = []
    for ins in md.disasm(code, method_rva):  # work in RVA space
        if ins.mnemonic == "ret":
            break
        if ins.mnemonic != "mov":
            continue
        # RIP-relative memory operand -> absolute (here: RVA) target.
        for op in ins.operands:
            if (op.type == X86_OP_MEM and op.mem.base in (0, X86_REG_RIP)
                    and op.mem.index == 0 and op.mem.disp > 0x1000):
                slots.append(ins.address + ins.size + op.mem.disp)
    return slots


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover Broken Arrow AES key + marker from native binaries.")
    ap.add_argument("--dll", default="GameAssembly.dll", help="path to GameAssembly.dll")
    ap.add_argument("--script", default="script.json",
                    help="Il2CppDumper script.json for this build")
    ap.add_argument("--out", default=None, help="optional path to write key.json")
    args = ap.parse_args()

    dll_path, script_path = Path(args.dll), Path(args.script)
    if not dll_path.is_file():
        return _fail(f"DLL not found: {dll_path}")
    if not script_path.is_file():
        return _fail(f"script.json not found: {script_path} (run Il2CppDumper first)")

    script = json.loads(script_path.read_text(encoding="utf-8"))
    strings = {s["Address"]: s["Value"] for s in script.get("ScriptString", [])}

    cctor_rva = find_method_rva(script, CCTOR_NAME)
    if cctor_rva is None:
        return _fail(f"could not find {CCTOR_NAME} in script.json "
                     "(class may have been renamed; inspect dump.cs)")

    slots = collect_literal_slots(dll_path, cctor_rva)
    values = [strings[s] for s in slots if s in strings]
    if not values:
        return _fail("no string literals resolved from .cctor; "
                     "inspect EncryptedFileManager..cctor in dump.cs manually")

    # Classify by content: AES key is 16/24/32 chars, marker is the short tag.
    key = next((v for v in values if len(v.encode()) in (16, 24, 32)), None)
    marker = next((v for v in values if v != key), None)

    print(f"Recovered string literals from {CCTOR_NAME}:")
    for v in values:
        print(f"  - {v!r}  ({len(v.encode())} bytes)")
    print()
    print(f"KEY    = {key!r}")
    print(f"MARKER = {marker!r}")

    if key is None:
        return _fail("no 16/24/32-byte literal found; key format may have changed")

    if args.out:
        Path(args.out).write_text(
            json.dumps({"key": key, "marker": marker}, indent=2), encoding="utf-8"
        )
        print(f"\nWrote {args.out}")
    print("\nUse with:  python tools/extract_database.py "
          f"--key {key} --marker {marker}")
    return 0


def _fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
