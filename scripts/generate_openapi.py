"""Generate or check the committed OpenAPI document deterministically."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

from dc_twin.api import app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "openapi" / "v1" / "openapi.json"
REGENERATE = "uv run python scripts/generate_openapi.py"


def unified_diff(committed: str, generated: str, name: str) -> str:
    lines = difflib.unified_diff(
        committed.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=f"{name} (committed)",
        tofile=f"{name} (generated)",
    )
    # A last line without a newline would run into the next one: mark it as diff and git do.
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines
    )


def check(rendered: str) -> int:
    name = TARGET.relative_to(ROOT).as_posix()
    if not TARGET.is_file():
        sys.stderr.write(f"{name} is missing.\nRegenerate it with: {REGENERATE}\n")
        return 1
    committed = TARGET.read_text(encoding="utf-8")
    if committed == rendered:
        return 0
    sys.stderr.write(
        f"{name} does not match the OpenAPI document the API generates:\n"
        + unified_diff(committed, rendered, name)
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
    TARGET.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
