from __future__ import annotations

import contextlib
import difflib
import importlib.util
import io
import json
import runpy
import shutil
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from tests.helpers import ROOT

HAS_API = importlib.util.find_spec("fastapi") is not None

if HAS_API:
    from dc_twin.api import app

CONTRACT = Path("contracts", "openapi", "v1", "openapi.json")
GENERATOR = Path("scripts", "generate_openapi.py")
MISMATCH = f"{CONTRACT.as_posix()} does not match the OpenAPI document the API generates:\n"
REGENERATE = "Regenerate it with: uv run python scripts/generate_openapi.py\n"


def copy_generator(root: Path) -> Path:
    script = root / GENERATOR
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / GENERATOR, script)
    return script


@unittest.skipUnless(HAS_API, "FastAPI test dependencies are not installed")
class OpenApiContractTests(unittest.TestCase):
    def test_committed_openapi_matches_its_generator(self) -> None:
        generated = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        committed = (ROOT / CONTRACT).read_text(encoding="utf-8")
        if committed != generated:
            diff = difflib.unified_diff(
                committed.splitlines(keepends=True),
                generated.splitlines(keepends=True),
                f"{CONTRACT.as_posix()} (committed)",
                f"{CONTRACT.as_posix()} (generated)",
            )
            self.fail(MISMATCH + "".join(diff) + REGENERATE)

    def test_check_reports_a_one_character_title_edit_as_a_unified_diff(self) -> None:
        title = f'    "title": {json.dumps(app.title, ensure_ascii=False)},\n'
        shortened = f'    "title": {json.dumps(app.title[:-1], ensure_ascii=False)},\n'

        def shorten_title(generated: str) -> str:
            self.assertEqual(generated.count(title), 1)
            return generated.replace(title, shortened)

        status, lines = self.check_edited_contract(shorten_title)
        self.assert_reported_as_diff(status, lines, ["-" + shortened, "+" + title])

    def test_check_marks_a_missing_final_newline_in_its_diff(self) -> None:
        status, lines = self.check_edited_contract(lambda generated: generated[:-1])
        self.assert_reported_as_diff(
            status, lines, ["-}\n", "\\ No newline at end of file\n", "+}\n"]
        )

    def test_check_reports_a_missing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = copy_generator(Path(directory))
            status, output = self.run_generator(script, "--check")
        self.assertEqual(status, 1)
        self.assertEqual(output, f"{CONTRACT.as_posix()} is missing.\n{REGENERATE}")

    def check_edited_contract(self, edit: Callable[[str], str]) -> tuple[object, list[str]]:
        """Generate the contract in a scratch tree, edit it, and check it as CI does."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = copy_generator(root)
            self.assertEqual(self.run_generator(script), (0, ""))
            self.assertEqual(self.run_generator(script, "--check"), (0, ""))
            target = root / CONTRACT
            edited = edit(target.read_text(encoding="utf-8"))
            target.write_text(edited, encoding="utf-8", newline="\n")
            status, output = self.run_generator(script, "--check")
        return status, output.splitlines(keepends=True)

    def assert_reported_as_diff(self, status: object, lines: list[str], changes: list[str]) -> None:
        self.assertEqual(status, 1)
        self.assertEqual(
            lines[:3],
            [
                MISMATCH,
                f"--- {CONTRACT.as_posix()} (committed)\n",
                f"+++ {CONTRACT.as_posix()} (generated)\n",
            ],
        )
        hunk = lines[3:-1]
        self.assertTrue(hunk[0].startswith("@@ "))
        self.assertEqual([line for line in hunk[1:] if not line.startswith(" ")], changes)
        self.assertEqual(lines[-1], REGENERATE)

    def run_generator(self, script: Path, *arguments: str) -> tuple[object, str]:
        """Run a copy of the generator as a script; return its exit status and stderr."""
        errors = io.StringIO()
        with (
            mock.patch.object(sys, "argv", [str(script), *arguments]),
            contextlib.redirect_stderr(errors),
            self.assertRaises(SystemExit) as raised,
        ):
            runpy.run_path(str(script), run_name="__main__")
        return raised.exception.code, errors.getvalue()


if __name__ == "__main__":
    unittest.main()
