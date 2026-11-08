from __future__ import annotations

import codecs
import contextlib
import copy
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
    from fastapi.testclient import TestClient

    from dc_twin.api import app

CONTRACT = Path("contracts", "openapi", "v1", "openapi.json")
SERVED = "/api/v1/openapi.json"
GENERATOR = Path("scripts", "generate_openapi.py")
MISMATCH = f"{CONTRACT.as_posix()} does not match the OpenAPI document the API generates:\n"
NOT_SERVED = f"{CONTRACT.as_posix()} does not match the document the API serves at {SERVED}:\n"
NOT_UTF8 = "It is not valid UTF-8; bytes that do not decode are shown as \\xNN.\n"
BYTE_ORDER_MARK = "It starts with a UTF-8 byte order mark; the generator writes none.\n"
CR_LINE_ENDINGS = "It has CRLF or CR line endings; the generator writes LF.\n"
ESCAPES = (
    "The diff shows a backslash as \\\\, a space at the end of a line as \\u0020, and a"
    " character outside printable ASCII as \\uNNNN, or \\UNNNNNNNN above U+FFFF.\n"
)
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


def canonical(document: object) -> str:
    """A parsed JSON document written out with sorted keys, indented, in ASCII."""
    return json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


@unittest.skipUnless(HAS_API, "FastAPI test dependencies are not installed")
class OpenApiContractTests(unittest.TestCase):
    def test_committed_openapi_matches_its_generator(self) -> None:
        generated = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        committed = (ROOT / CONTRACT).read_bytes()
        if committed != generated.encode():
            # The verdict is this test's own; the script only words the difference.
            describe = runpy.run_path(str(ROOT / GENERATOR))["describe_difference"]
            self.fail(MISMATCH + describe(committed, generated, CONTRACT.as_posix()) + REGENERATE)

    def test_api_serves_the_committed_contract(self) -> None:
        with TestClient(app) as client:
            response = client.get(SERVED)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        # The API serves the document compact, so both are compared written out alike.
        committed = canonical(json.loads((ROOT / CONTRACT).read_bytes()))
        served = canonical(response.json())
        if served != committed:
            diff = difflib.unified_diff(
                lines_of(committed),
                lines_of(served),
                f"{CONTRACT.as_posix()} (committed)",
                f"{SERVED} (served)",
            )
            self.fail(NOT_SERVED + "".join(diff))

    def test_a_served_title_edit_is_reported_as_a_unified_diff(self) -> None:
        served = copy.deepcopy(app.openapi())
        served["info"]["title"] = app.title[:-1]
        with (
            mock.patch.object(app, "openapi", return_value=served),
            self.assertRaises(AssertionError) as raised,
        ):
            self.test_api_serves_the_committed_contract()
        lines = lines_of(str(raised.exception))
        header = [
            NOT_SERVED,
            f"--- {CONTRACT.as_posix()} (committed)\n",
            f"+++ {SERVED} (served)\n",
        ]
        self.assertEqual(lines[: len(header)], header)
        self.assertTrue(lines[len(header)].startswith("@@ "))
        self.assertEqual(
            [line for line in lines[len(header) + 1 :] if not line.startswith(" ")],
            ["-" + title_line(app.title), "+" + title_line(app.title[:-1])],
        )

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

    def test_check_names_a_byte_order_mark_and_crlf_line_endings_together(self) -> None:
        # Windows PowerShell 5.1 writes both: Get-Content | Set-Content -Encoding UTF8.
        self.assertEqual(
            self.check_edited_contract(
                lambda generated: codecs.BOM_UTF8 + generated.replace(b"\n", b"\r\n")
            ),
            (1, [MISMATCH, BYTE_ORDER_MARK, CR_LINE_ENDINGS, REGENERATE]),
        )

    def test_check_shows_bytes_that_are_not_utf8_as_escapes(self) -> None:
        title = title_line(app.title)
        latin1 = title.encode().replace(b'",\n', b'\xe9",\n')
        status, lines = self.check_edited_contract(self.with_title_line(latin1))
        self.assert_reported_as_diff(
            status,
            lines,
            ["-" + title.replace('",\n', '\\xe9",\n'), "+" + title],
            [NOT_UTF8, ESCAPES],
        )

    def test_check_splits_its_diff_at_line_feeds_only(self) -> None:
        title = title_line(app.title)
        self.assert_shown_escaped(
            title.replace('",\n', '\u2028",\n'), title.replace('",\n', '\\u2028",\n')
        )

    def test_check_escapes_a_space_at_the_end_of_a_line(self) -> None:
        title = title_line(app.title)
        self.assert_shown_escaped(title.replace(",\n", ", \n"), title.replace(",\n", ",\\u0020\n"))

    def test_check_escapes_a_no_break_space(self) -> None:
        title = title_line(app.title)
        self.assert_shown_escaped(title.replace(": ", ":\u00a0"), title.replace(": ", ":\\u00a0"))

    def test_check_escapes_a_zero_width_space(self) -> None:
        title = title_line(app.title)
        self.assert_shown_escaped(
            title.replace('",\n', '\u200b",\n'), title.replace('",\n', '\\u200b",\n')
        )

    def test_check_escapes_a_byte_order_mark_inside_a_line(self) -> None:
        title = title_line(app.title)
        self.assert_shown_escaped(
            title.replace('",\n', '\ufeff",\n'), title.replace('",\n', '\\ufeff",\n')
        )

    def test_check_escapes_a_nul_byte(self) -> None:
        title = title_line(app.title)
        self.assert_shown_escaped(
            title.replace('",\n', '\x00",\n'), title.replace('",\n', '\\u0000",\n')
        )

    def test_check_shows_a_json_escape_apart_from_the_character_it_encodes(self) -> None:
        # In JSON, the six characters \u00a0 stand for a no-break space: the diff must not
        # show them as it shows the no-break space itself.
        title = title_line(app.title)
        self.assert_shown_escaped(
            title.replace('",\n', '\\u00a0",\n'), title.replace('",\n', '\\\\u00a0",\n')
        )

    def test_check_escapes_every_line_its_diff_shows(self) -> None:
        # The document the API generates is ASCII, so this calls the script's description
        # of a difference on made-up texts, in which an unchanged line holds a no-break space.
        describe = runpy.run_path(str(ROOT / GENERATOR))["describe_difference"]
        generated = '{\n  "a": "x\u00a0y",\n  "b": 2\n}\n'
        committed = generated.replace('"b": 2', '"b": 1').encode()
        self.assertEqual(
            describe(committed, generated, "made-up.json"),
            ESCAPES
            + "--- made-up.json (committed)\n+++ made-up.json (generated)\n@@ -1,4 +1,4 @@\n"
            + ' {\n   "a": "x\\u00a0y",\n-  "b": 1\n+  "b": 2\n }\n',
        )

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

    def assert_shown_escaped(self, edited: str, shown: str) -> None:
        """Check a contract whose title line reads `edited`: its diff must show it as `shown`."""
        status, lines = self.check_edited_contract(self.with_title_line(edited.encode()))
        self.assert_reported_as_diff(
            status, lines, ["-" + shown, "+" + title_line(app.title)], [ESCAPES]
        )

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
