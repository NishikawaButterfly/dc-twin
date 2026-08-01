"""Check committed contract syntax, fixtures, deterministic replay, and web safety sinks."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from dc_twin.engine import simulate
from dc_twin.reference import ReferenceCatalog

ROOT = Path(__file__).resolve().parents[1]
MINIMUM_CONTRACT_FILES = 3


def main() -> int:
    failures: list[str] = []
    schema_paths = sorted(
        path
        for path in (ROOT / "contracts").rglob("*.json")
        # The generated OpenAPI document is an OpenAPI 3.x file, not a JSON Schema.
        if "openapi" not in path.parts
    )
    if len(schema_paths) < MINIMUM_CONTRACT_FILES:
        failures.append("Expected at least three committed JSON contract files.")
    for path in schema_paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{path.relative_to(ROOT)} is invalid JSON: {exc}")
            continue
        if (
            not isinstance(value, dict)
            or value.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        ):
            failures.append(f"{path.relative_to(ROOT)} is not declared as JSON Schema 2020-12.")
    try:
        catalog = ReferenceCatalog.load()
        for reference in catalog.scenarios.values():
            first = simulate(catalog.snapshot, reference.scenario)
            second = simulate(catalog.snapshot, reference.scenario)
            if first["computation_hash"] != second["computation_hash"]:
                failures.append(f"Replay drift for {reference.scenario.scenario_id}.")
    except Exception as exc:
        failures.append(f"Reference contract validation failed: {exc}")
    web_script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    failures.extend(
        f"Unsafe web sink matched: {pattern}"
        for pattern in (r"\.innerHTML\b", r"\beval\s*\(", r"new\s+Function\s*\(")
        if re.search(pattern, web_script)
    )
    if failures:
        sys.stderr.write("Contract checks failed:\n- " + "\n- ".join(failures) + "\n")
        return 1
    sys.stdout.write(
        f"Validated {len(schema_paths)} contracts "
        f"and {len(catalog.scenarios)} reference scenarios.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
