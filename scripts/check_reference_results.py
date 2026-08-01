"""Reconcile engine output against hand-calculated committed expectations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dc_twin.canonical import load_path_strict
from dc_twin.engine import simulate
from dc_twin.reference import ReferenceCatalog

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PATH = ROOT / "examples" / "synthetic" / "expected" / "reference-metrics.json"


def main() -> int:
    expected_value = load_path_strict(EXPECTED_PATH)
    if not isinstance(expected_value, dict) or not isinstance(
        expected_value.get("scenarios"), dict
    ):
        raise ValueError("Independent expectations must contain a scenarios object.")
    catalog = ReferenceCatalog.load()
    failures: list[str] = []
    evidence: dict[str, Any] = {}
    for scenario_id, expected in sorted(expected_value["scenarios"].items()):
        if scenario_id not in catalog.scenarios:
            failures.append(f"Missing scenario fixture: {scenario_id}")
            continue
        reference = catalog.scenarios[scenario_id]
        result = simulate(catalog.snapshot, reference.scenario)
        expected_metrics = expected["metrics"]
        actual_metrics = result["metrics"]
        for key, expected_value_for_key in expected_metrics.items():
            if actual_metrics.get(key) != expected_value_for_key:
                failures.append(
                    f"{scenario_id}.{key}: expected {expected_value_for_key!r}, "
                    f"received {actual_metrics.get(key)!r}"
                )
        initial_ups_energy = catalog.snapshot.component_by_id["ups-a"].usable_energy_mj or 0
        final_ups_energy = result["timeline"][-1]["battery_energy_mj"]["ups-a"]
        actual_discharge = initial_ups_energy - final_ups_energy
        if actual_discharge != expected["ups_a_discharge_mj"]:
            failures.append(
                f"{scenario_id}.ups_a_discharge_mj: expected {expected['ups_a_discharge_mj']}, "
                f"received {actual_discharge}"
            )
        if "outage_start_ms" in expected:
            outage = [segment for segment in result["timeline"] if segment["unserved_w"] > 0]
            actual_start = outage[0]["start_ms"] if outage else None
            actual_end = outage[-1]["end_ms"] if outage else None
            if (
                actual_start != expected["outage_start_ms"]
                or actual_end != expected["outage_end_ms"]
            ):
                failures.append(
                    f"{scenario_id}.outage: expected {expected['outage_start_ms']}.."
                    f"{expected['outage_end_ms']}, received {actual_start}..{actual_end}"
                )
        for code, expected_time in expected.get("alarm_times_ms", {}).items():
            actual_times = [alarm["time_ms"] for alarm in result["alarms"] if alarm["code"] == code]
            if actual_times != [expected_time]:
                failures.append(
                    f"{scenario_id}.{code}: expected [{expected_time}], received {actual_times}"
                )
        evidence[scenario_id] = {
            "computation_hash": result["computation_hash"],
            "metrics": actual_metrics,
            "ups_a_discharge_mj": actual_discharge,
        }
    if failures:
        sys.stderr.write("Reference reconciliation failed:\n- " + "\n- ".join(failures) + "\n")
        return 1
    sys.stdout.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
