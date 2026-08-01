from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from dc_twin.canonical import canonical_dumps, load_path_strict, loads_strict, sha256_json
from dc_twin.errors import ContractError


class CanonicalJsonTests(unittest.TestCase):
    def test_hash_is_independent_of_mapping_order(self) -> None:
        self.assertEqual(sha256_json({"b": 2, "a": 1}), sha256_json({"a": 1, "b": 2}))
        self.assertEqual(canonical_dumps({"b": 2, "a": 1}), '{"a":1,"b":2}')

    def test_duplicate_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "Duplicate JSON key"):
            loads_strict('{"a": 1, "a": 2}')

    def test_non_finite_constants_are_rejected(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ContractError):
                loads_strict(f'{{"value": {value}}}')
        with self.assertRaises(ContractError):
            canonical_dumps({"nested": [math.inf]})

    def test_invalid_and_oversized_json_are_rejected(self) -> None:
        with self.assertRaises(ContractError):
            loads_strict("{")
        with self.assertRaises(ContractError):
            loads_strict('"12345"', max_bytes=4)

    def test_missing_oversized_and_non_utf8_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ContractError, "Cannot read"):
                load_path_strict(root / "absent.json")
            oversized = root / "oversized.json"
            oversized.write_text('{"key": "' + "x" * 32 + '"}', encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "exceeds"):
                load_path_strict(oversized, max_bytes=16)
            invalid = root / "invalid-encoding.json"
            invalid.write_bytes(b'{"key": "\xff\xfe"}')
            with self.assertRaisesRegex(ContractError, "UTF-8"):
                load_path_strict(invalid)


if __name__ == "__main__":
    unittest.main()
