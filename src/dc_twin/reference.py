"""Allowlisted synthetic reference fixture catalog."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from dc_twin.canonical import load_path_strict, loads_strict
from dc_twin.errors import ContractError
from dc_twin.models import Scenario, Snapshot
from dc_twin.validation import parse_scenario, parse_snapshot


@dataclass(frozen=True, slots=True)
class ReferenceSnapshot:
    snapshot: Snapshot
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReferenceScenario:
    scenario: Scenario
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReferenceCatalog:
    snapshots: dict[str, ReferenceSnapshot]
    scenarios: dict[str, ReferenceScenario]

    @classmethod
    def load(cls) -> ReferenceCatalog:
        """Load committed synthetic fixtures from source or installed package data."""

        source_root = Path(__file__).resolve().parents[2] / "examples" / "synthetic"
        if source_root.is_dir():
            snapshot_values = [
                load_path_strict(path) for path in sorted(source_root.glob("*.snapshot.json"))
            ]
            scenario_values = [
                load_path_strict(path)
                for path in sorted((source_root / "scenarios").glob("*.json"))
            ]
        else:
            package_root = resources.files("dc_twin").joinpath("reference")
            snapshot_values = [
                loads_strict(item.read_text(encoding="utf-8"))
                for item in sorted(package_root.iterdir(), key=lambda entry: entry.name)
                if item.name.endswith(".snapshot.json")
            ]
            scenario_root = package_root.joinpath("scenarios")
            scenario_values = [
                loads_strict(item.read_text(encoding="utf-8"))
                for item in sorted(scenario_root.iterdir(), key=lambda entry: entry.name)
                if item.name.endswith(".json")
            ]
        snapshots: dict[str, ReferenceSnapshot] = {}
        for snapshot_value in snapshot_values:
            if not isinstance(snapshot_value, dict):
                raise ContractError(
                    "reference.snapshot_shape", "Reference snapshot must be an object."
                )
            snapshot_raw = dict(snapshot_value)
            snapshot = parse_snapshot(snapshot_raw)
            if snapshot.snapshot_id in snapshots:
                raise ContractError(
                    "reference.duplicate_snapshot",
                    f"Duplicate reference snapshot {snapshot.snapshot_id}.",
                )
            snapshots[snapshot.snapshot_id] = ReferenceSnapshot(snapshot=snapshot, raw=snapshot_raw)
        if not snapshots:
            raise ContractError(
                "reference.no_snapshots", "No synthetic reference snapshots were found."
            )
        scenarios: dict[str, ReferenceScenario] = {}
        for value in scenario_values:
            if not isinstance(value, dict):
                raise ContractError(
                    "reference.scenario_shape", "Reference scenario must be an object."
                )
            raw = dict(value)
            reference_snapshot = snapshots.get(str(raw.get("snapshot_id")))
            if reference_snapshot is None:
                raise ContractError(
                    "reference.unknown_snapshot",
                    f"Reference scenario {raw.get('scenario_id')!r} references an unknown "
                    "snapshot.",
                )
            scenario = parse_scenario(raw, reference_snapshot.snapshot)
            if scenario.scenario_id in scenarios:
                raise ContractError(
                    "reference.duplicate_scenario",
                    f"Duplicate reference scenario {scenario.scenario_id}.",
                )
            scenarios[scenario.scenario_id] = ReferenceScenario(scenario=scenario, raw=raw)
        if not scenarios:
            raise ContractError(
                "reference.no_scenarios", "No synthetic reference scenarios were found."
            )
        return cls(snapshots=snapshots, scenarios=scenarios)

    def snapshot_for(self, scenario: Scenario) -> ReferenceSnapshot:
        return self.snapshots[scenario.snapshot_id]

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "scenario_id": item.scenario.scenario_id,
                "label": item.scenario.label,
                "description": _scenario_description(item.scenario.scenario_id),
                "modeled_redundancy": _scenario_redundancy(item.scenario.scenario_id),
                "horizon_ms": item.scenario.horizon_ms,
                "event_count": len(item.scenario.events),
                "data_classification": "synthetic",
            }
            for item in sorted(
                self.scenarios.values(), key=lambda value: value.scenario.scenario_id
            )
        ]


def _scenario_description(scenario_id: str) -> str:
    descriptions = {
        "REF-DC-2N-HEALTHY": "Healthy two-path reference operation with no injected events.",
        "REF-DC-2N-GEN-SUCCESS": (
            "Planned path maintenance followed by utility loss, UPS bridge, "
            "and successful generator start."
        ),
        "REF-DC-2N-001": (
            "Composite maintenance, utility loss, generator-start failure, "
            "UPS depletion, and service restoration."
        ),
        "REF-DC-N-001": (
            "Single-path utility loss, UPS ride-through to depletion, and utility restoration."
        ),
        "REF-DC-NP1-001": (
            "Single UPS failure absorbed by the reserve UPS with a bounded battery bridge."
        ),
    }
    return descriptions.get(scenario_id, "Synthetic deterministic reference scenario.")


def _scenario_redundancy(scenario_id: str) -> str:
    return "two_n" if scenario_id == "REF-DC-2N-HEALTHY" else "event_dependent"
