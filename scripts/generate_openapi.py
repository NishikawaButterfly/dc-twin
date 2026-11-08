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


def lines_of(text: str) -> list[str]:
    # The file's lines end at LF. str.splitlines() would also split at U+2028
    # and other separators, which the generator writes unescaped in strings.
    return io.StringIO(text, newline="\n").readlines()


def unified_diff(committed: str, generated: str, name: str) -> str:
    lines = difflib.unified_diff(
        lines_of(committed),
        lines_of(generated),
        fromfile=f"{name} (committed)",
        tofile=f"{name} (generated)",
    )
    # A last line without a newline would run into the next one: mark it as diff and git do.
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines
    )


def describe_difference(committed: bytes, generated: str, name: str) -> str:
    """Say how the committed bytes differ from the generated document.

    What a diff cannot show is named first, one line each: bytes that are not
    UTF-8, a byte order mark, CR line endings. The diff that follows compares
    the text with those set aside, and is empty when nothing else differs.
    """
    notes: list[str] = []
    try:
        text = committed.decode("utf-8")
    except UnicodeDecodeError:
        text = committed.decode("utf-8", errors="backslashreplace")
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
