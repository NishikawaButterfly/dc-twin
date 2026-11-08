from __future__ import annotations

import unittest
from importlib.metadata import distribution

from tests.helpers import ROOT


class LicenseMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.installed = distribution("dc-twin")

    def test_license_is_declared_as_an_spdx_expression(self) -> None:
        metadata = self.installed.metadata
        self.assertEqual(metadata.get("License-Expression"), "MIT")
        self.assertIsNone(metadata.get("License"))
        classifiers = metadata.get_all("Classifier") or []
        self.assertEqual([item for item in classifiers if item.startswith("License ::")], [])

    def test_license_file_ships_identical_to_the_repository_copy(self) -> None:
        self.assertEqual(self.installed.metadata.get_all("License-File"), ["LICENSE"])
        marker = ".dist-info/licenses/"
        shipped = {
            path.as_posix().split(marker, 1)[1]: path
            for path in self.installed.files or []
            if marker in path.as_posix()
        }
        self.assertEqual(sorted(shipped), ["LICENSE"])
        self.assertEqual(shipped["LICENSE"].read_binary(), (ROOT / "LICENSE").read_bytes())


if __name__ == "__main__":
    unittest.main()
