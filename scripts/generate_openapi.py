"""Generate or check the committed OpenAPI document deterministically."""

from __future__ import annotations

import argparse
import difflib
import io
import json
import sys
from pathlib import Path

from dc_twin.api import app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "openapi" / "v1" / "openapi.json"
REGENERATE = "uv run python scripts/generate_openapi.py"
ESCAPES = (
    "The diff shows a backslash as \\\\, a space at the end of a line as \\u0020, and a"
    " character outside printable ASCII as \\uNNNN, or \\UNNNNNNNN above U+FFFF.\n"
)


def lines_of(text: str) -> list[str]:
    # The file's lines end at LF. str.splitlines() would also split at U+2028
    # and other separators, which the generator writes unescaped in strings.
    return io.StringIO(text, newline="\n").readlines()


def reads_as_written(line: str) -> bool:
    """Whether a line shows what it holds: printable ASCII, no backslash, no space at its end."""
    text = line.removesuffix("\n")
    return text.isascii() and text.isprintable() and "\\" not in text and not text.endswith(" ")


def escape(character: str) -> str:
    """Write a character as ESCAPES says, or a byte that is not UTF-8 as \\xNN."""
    if character == "\\":
        return "\\\\"
    if " " <= character <= "~":
        return character
    if "\udc80" <= character <= "\udcff":
        # A byte that is not UTF-8, which decoding with surrogateescape turned into this.
        return f"\\x{character.encode('utf-8', 'surrogateescape')[0]:02x}"
    return f"\\u{ord(character):04x}" if character <= "\uffff" else f"\\U{ord(character):08x}"


def escaped(line: str) -> str:
    """Write a line with each character escaped, and each space at its end as \\u0020."""
    text = line.removesuffix("\n")
    kept = text.rstrip(" ")
    return "".join(map(escape, kept)) + "\\u0020" * (len(text) - len(kept)) + line[len(text) :]


def unified_diff(committed: str, generated: str, name: str) -> str:
    """Diff the committed text against the generated one, line by line.

    When every line the diff shows reads as written, it shows them as they
    are. Otherwise it shows every line escaped, after the ESCAPES line, so
    that no character hides and no two different lines read alike.
    """
    old, new = lines_of(committed), lines_of(generated)
    labels = (f"{name} (committed)", f"{name} (generated)")
    lines = list(difflib.unified_diff(old, new, *labels))
    legend = ""
    # The first two lines name the files. Each later line opens a hunk with "@@",
    # or holds a line of either text after " ", "-" or "+".
    if not all(reads_as_written(line[1:]) for line in lines[2:] if not line.startswith("@@")):
        old, new = list(map(escaped, old)), list(map(escaped, new))
        lines = list(difflib.unified_diff(old, new, *labels))
        legend = ESCAPES
    # A last line without a newline would run into the next one: mark it as diff and git do.
    return legend + "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines
    )


def describe_difference(committed: bytes, generated: str, name: str) -> str:
    """Say how the committed bytes differ from the generated document.

    Three differences are named first, one line each: bytes that are not
    UTF-8, a byte order mark at the start, CRLF or CR line endings. The diff
    that follows compares the text with the mark and the CRs set aside, so
    it is empty when nothing else differs, and shows the bytes that are not
    UTF-8 as escapes.
    """
    notes: list[str] = []
    try:
        text = committed.decode("utf-8")
    except UnicodeDecodeError:
        text = committed.decode("utf-8", errors="surrogateescape")
        notes.append("It is not valid UTF-8; bytes that do not decode are shown as \\xNN.")
    if text.startswith("\ufeff"):
        text = text[1:]
        notes.append("It starts with a UTF-8 byte order mark; the generator writes none.")
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        notes.append("It has CRLF or CR line endings; the generator writes LF.")
    return "".join(f"{note}\n" for note in notes) + unified_diff(text, generated, name)


def check(rendered: str) -> int:
    name = TARGET.relative_to(ROOT).as_posix()
    if not TARGET.is_file():
        sys.stderr.write(f"{name} is missing.\nRegenerate it with: {REGENERATE}\n")
        return 1
    committed = TARGET.read_bytes()
    if committed == rendered.encode():
        return 0
    sys.stderr.write(
        f"{name} does not match the OpenAPI document the API generates:\n"
        + describe_difference(committed, rendered, name)
        + f"Regenerate it with: {REGENERATE}\n"
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rendered = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.check:
        return check(rendered)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(rendered.encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
