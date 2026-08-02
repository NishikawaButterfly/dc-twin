"""Independent fixture readers and small valid contract builders."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from dc_twin.canonical import load_path_strict

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "synthetic"


def reference_snapshot_data(filename: str = "reference-2n.snapshot.json") -> dict[str, Any]:
    value = load_path_strict(EXAMPLES / filename)
    assert isinstance(value, dict)
    return copy.deepcopy(value)


def reference_scenario_data(filename: str) -> dict[str, Any]:
    value = load_path_strict(EXAMPLES / "scenarios" / filename)
    assert isinstance(value, dict)
    return copy.deepcopy(value)


def minimal_snapshot_data() -> dict[str, Any]:
    return {
        "schema_id": "dc-twin.electrical-design-snapshot",
        "schema_version": "1.0.0",
        "snapshot_id": "minimal",
        "design_revision": "1",
        "data_classification": "synthetic",
        "provenance": {
            "title": "Synthetic minimal topology",
            "created_by": "test suite",
            "method": "Hand-authored test fixture",
        },
        "units": {"power": "W", "energy": "mJ", "time": "ms"},
        "assumptions": ["Lossless active-power capacity."],
        "components": [
            {
                "id": "source",
                "label": "Synthetic source",
                "kind": "utility",
                "path": "A",
                "capacity_w": 100,
                "initial_status": "available",
            },
            {
                "id": "bus",
                "label": "Synthetic bus",
                "kind": "switchgear",
                "path": "A",
                "capacity_w": 100,
                "initial_status": "available",
            },
            {
                "id": "load",
                "label": "Synthetic load",
                "kind": "load",
                "path": "shared",
                "capacity_w": 100,
                "initial_status": "available",
                "demand_w": 80,
                "priority": 1,
                "service_order": 1,
            },
        ],
        "connections": [
            {
                "id": "source-bus",
                "from_component": "source",
                "to_component": "bus",
                "capacity_w": 100,
                "initial_closed": True,
            },
            {
                "id": "bus-load",
                "from_component": "bus",
                "to_component": "load",
                "capacity_w": 100,
                "initial_closed": True,
            },
        ],
        "redundancy_groups": [{"id": "n", "mode": "N", "members": ["source"]}],
    }


def minimal_scenario_data(*, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_id": "dc-twin.scenario",
        "schema_version": "1.0.0",
        "scenario_id": "minimal-scenario",
        "label": "Synthetic minimal scenario",
        "snapshot_id": "minimal",
        "horizon_ms": 1_000,
        "resolution_ms": 100,
        "data_classification": "synthetic",
        "events": events or [],
    }
