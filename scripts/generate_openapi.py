"""Generate or check the committed OpenAPI document deterministically."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dc_twin.api import app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "openapi" / "v1" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rendered = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.check:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != rendered:
            sys.stderr.write("Committed OpenAPI document is missing or stale.\n")
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
