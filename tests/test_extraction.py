import base64
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import extract_database as database
import extract_localization as localization


class ExtractionTests(unittest.TestCase):
    def encrypted(self, value):
        iv = bytes(16)
        ciphertext = AES.new(database.DEFAULT_KEY.encode(), AES.MODE_CBC, iv).encrypt(
            pad(json.dumps(value).encode(), 16)
        )
        return base64.b64encode(database.DEFAULT_MARKER.encode() + iv + ciphertext).decode()

    def run_database(self, fields, combined_flag=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "database.asset"
            asset.write_text("\n".join(f"  {key}: {value}" for key, value in fields.items()))
            out = root / "output"
            (out / "tables").mkdir(parents=True)
            existing = out / "tables" / "Units.json"
            existing.write_text("old build")
            combined = out / "database.json"
            combined.write_text("old combined build")
            args = ["extract", "--asset", str(asset), "--out", str(out)]
            if combined_flag:
                args.append("--combined")
            with patch.object(sys, "argv", args):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = database.main()
            return result, existing.read_text(), combined.read_text(), len(list((out / "tables").glob("*.json")))

    def test_missing_table_keeps_previous_build(self):
        self.assertEqual(self.run_database({"Units": self.encrypted([{"Id": 1}])}),
                         (1, "old build", "old combined build", 1))

    def test_corrupt_late_table_keeps_previous_build(self):
        fields = {name: self.encrypted([{"Id": 1}]) for name in database.FIELD_TO_TABLE}
        fields["TransportAvailabilitiesJson"] = "not base64"
        self.assertEqual(self.run_database(fields), (1, "old build", "old combined build", 1))

    def test_duplicate_ids_keep_previous_build(self):
        fields = {name: self.encrypted([{"Id": 1}]) for name in database.FIELD_TO_TABLE}
        fields["WeaponsJson"] = self.encrypted([{"Id": 1}, {"Id": 1}])
        self.assertEqual(self.run_database(fields), (1, "old build", "old combined build", 1))

    def test_complete_build_writes_all_tables(self):
        fields = {name: self.encrypted([{"Id": 1}]) for name in database.FIELD_TO_TABLE}
        result, units, combined, count = self.run_database(fields)
        self.assertEqual((result, count), (0, 24))
        self.assertEqual(json.loads(units), [{"Id": 1}])
        self.assertEqual(set(json.loads(combined)), set(database.FIELD_TO_TABLE.values()))

    def test_localization_mismatch_does_not_truncate(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys, values = Path(tmp) / "keys.json", Path(tmp) / "eng.json"
            keys.write_text('["keys", "one", "two"]')
            values.write_text('["eng", "One"]')
            with self.assertRaisesRegex(ValueError, "length mismatch"):
                localization.build_map(keys, values)

    def test_existing_combined_dump_is_refreshed_without_flag(self):
        fields = {name: self.encrypted([{"Id": 1}]) for name in database.FIELD_TO_TABLE}
        result, units, combined, count = self.run_database(fields, combined_flag=False)
        self.assertEqual((result, count), (0, 24))
        self.assertEqual(json.loads(combined)["Units"], json.loads(units))

    def test_manifest_has_no_crypto_dependency(self):
        result = subprocess.run([sys.executable, "-S", str(TOOLS / "extract_manifest.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_untranslated_localization_entries_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys, values = Path(tmp) / "keys.json", Path(tmp) / "eng.json"
            keys.write_text('["keys", "untranslated"]')
            values.write_text('["eng", null]')
            self.assertEqual(localization.build_map(keys, values), {"keys": "eng", "untranslated": None})


if __name__ == "__main__":
    unittest.main()
