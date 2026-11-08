from __future__ import annotations

import codecs
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
from collections.abc import Callable, Sequence
from pathlib import Path
from unittest import mock

from tests.helpers import ROOT

HAS_API = importlib.util.find_spec("fastapi") is not None

if HAS_API:
    from dc_twin.api import app

CONTRACT = Path("contracts", "openapi", "v1", "openapi.json")
GENERATOR = Path("scripts", "generate_openapi.py")
MISMATCH = f"{CONTRACT.as_posix()} does not match the OpenAPI document the API generates:\n"
NOT_UTF8 = "It is not valid UTF-8; bytes that do not decode are shown as \\xNN.\n"
BYTE_ORDER_MARK = "It starts with a UTF-8 byte order mark; the generator writes none.\n"
CR_LINE_ENDINGS = "It has CRLF or CR line endings; the generator writes LF.\n"
REGENERATE = "Regenerate it with: uv run python scripts/generate_openapi.py\n"


def copy_generator(root: Path) -> Path:
    script = root / GENERATOR
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / GENERATOR, script)
    return script


def title_line(title: str) -> str:
    """The line of the contract that gives the API title, as the generator writes it."""
    return f'    "title": {json.dumps(title, ensure_ascii=False)},\n'


def lines_of(text: str) -> list[str]:
    """Split at LF only, keeping it: str.splitlines() also splits at U+2028 and others."""
    return io.StringIO(text, newline="\n").readlines()


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
        shortened = title_line(app.title[:-1])
        status, lines = self.check_edited_contract(self.with_title_line(shortened.encode()))
        self.assert_reported_as_diff(status, lines, ["-" + shortened, "+" + title_line(app.title)])

    def test_check_marks_a_missing_final_newline_in_its_diff(self) -> None:
        status, lines = self.check_edited_contract(lambda generated: generated[:-1])
        self.assert_reported_as_diff(
            status, lines, ["-}\n", "\\ No newline at end of file\n", "+}\n"]
        )

    def test_check_names_cr_and_crlf_line_endings(self) -> None:
        endings: dict[str, Callable[[bytes], bytes]] = {
            "CRLF": lambda generated: generated.replace(b"\n", b"\r\n"),
            "CR": lambda generated: generated.replace(b"\n", b"\r"),
            "one CRLF": lambda generated: generated.replace(b"\n", b"\r\n", 1),
        }
        for name, edit in endings.items():
            self.assertEqual(
                self.check_edited_contract(edit),
                (1, [MISMATCH, CR_LINE_ENDINGS, REGENERATE]),
                name,
            )

    def test_check_names_a_byte_order_mark(self) -> None:
        self.assertEqual(
            self.check_edited_contract(lambda generated: codecs.BOM_UTF8 + generated),
            (1, [MISMATCH, BYTE_ORDER_MARK, REGENERATE]),
        )

    def test_check_shows_bytes_that_are_not_utf8_as_escapes(self) -> None:
        title = title_line(app.title)
        latin1 = title.encode().replace(b'",\n', b'\xe9",\n')
        status, lines = self.check_edited_contract(self.with_title_line(latin1))
        self.assert_reported_as_diff(
            status, lines, ["-" + title.replace('",\n', '\\xe9",\n'), "+" + title], [NOT_UTF8]
        )

    def test_check_splits_its_diff_at_line_feeds_only(self) -> None:
        separated = title_line(app.title + "\u2028")
        status, lines = self.check_edited_contract(self.with_title_line(separated.encode()))
        self.assert_reported_as_diff(status, lines, ["-" + separated, "+" + title_line(app.title)])

    def test_check_reports_a_missing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = copy_generator(Path(directory))
            status, output = self.run_generator(script, "--check")
        self.assertEqual(status, 1)
        self.assertEqual(output, f"{CONTRACT.as_posix()} is missing.\n{REGENERATE}")

    def with_title_line(self, line: bytes) -> Callable[[bytes], bytes]:
        """An edit that puts `line` in place of the title line the generator wrote."""
        title = title_line(app.title).encode()

        def edit(generated: bytes) -> bytes:
            self.assertEqual(generated.count(title), 1)
            return generated.replace(title, line)

        return edit

    def check_edited_contract(self, edit: Callable[[bytes], bytes]) -> tuple[object, list[str]]:
        """Generate the contract in a scratch tree, edit its bytes, and check it as CI does."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = copy_generator(root)
            self.assertEqual(self.run_generator(script), (0, ""))
            target = root / CONTRACT
            generated = target.read_bytes()
            self.assertNotIn(b"\r", generated)
            self.assertEqual(self.run_generator(script, "--check"), (0, ""))
            edited = edit(generated)
            self.assertNotEqual(edited, generated)
            target.write_bytes(edited)
            status, output = self.run_generator(script, "--check")
        return status, lines_of(output)

    def assert_reported_as_diff(
        self, status: object, lines: list[str], changes: list[str], notes: Sequence[str] = ()
    ) -> None:
        self.assertEqual(status, 1)
        header = [
            MISMATCH,
            *notes,
            f"--- {CONTRACT.as_posix()} (committed)\n",
            f"+++ {CONTRACT.as_posix()} (generated)\n",
        ]
        self.assertEqual(lines[: len(header)], header)
        hunk = lines[len(header) : -1]
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
