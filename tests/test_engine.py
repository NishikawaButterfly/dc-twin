from __future__ import annotations

import copy
import unittest

from dc_twin.canonical import sha256_json
from dc_twin.engine import simulate, verify_replay
from dc_twin.errors import ContractError, TopologyError
from dc_twin.validation import parse_scenario, parse_snapshot
from tests.helpers import (
    minimal_scenario_data,
    minimal_snapshot_data,
    reference_scenario_data,
    reference_snapshot_data,
)


class ReferenceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = parse_snapshot(reference_snapshot_data())

    def _run(self, filename: str) -> dict[str, object]:
        scenario = parse_scenario(reference_scenario_data(filename), self.snapshot)
        return simulate(self.snapshot, scenario)

    def test_healthy_scenario_is_fully_served(self) -> None:
        result = self._run("healthy.scenario.json")
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        self.assertEqual(metrics["unserved_energy_mj"], 0)
        self.assertEqual(metrics["service_ratio_ppm"], 1_000_000)
        self.assertEqual(metrics["modeled_redundancy_state"], "two_n")

    def test_composite_reference_matches_independent_calculation(self) -> None:
        result = self._run("composite-failure.scenario.json")
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        self.assertEqual(metrics["demanded_energy_mj"], 960_000_000_000)
        self.assertEqual(metrics["served_energy_mj"], 908_800_000_000)
        self.assertEqual(metrics["unserved_energy_mj"], 51_200_000_000)
        self.assertEqual(metrics["service_ratio_ppm"], 946_667)
        self.assertEqual(metrics["interruption_duration_ms"], 32_000)
        self.assertEqual(metrics["interruption_count"], 1)
        timeline = result["timeline"]
        assert isinstance(timeline, list)
        outage = [segment for segment in timeline if segment["unserved_w"] > 0]
        self.assertEqual(outage[0]["start_ms"], 390_000)
        self.assertEqual(outage[-1]["end_ms"], 422_000)
        alarms = result["alarms"]
        assert isinstance(alarms, list)
        alarm_times = {(alarm["code"], alarm["time_ms"]) for alarm in alarms}
        self.assertIn(("ups_low_energy", 336_000), alarm_times)
        self.assertIn(("ups_energy_depleted", 390_000), alarm_times)
        self.assertIn(("load_unserved", 390_000), alarm_times)

    def test_generator_success_has_exact_ups_bridge_energy_and_no_outage(self) -> None:
        result = self._run("generator-success.scenario.json")
        metrics = result["metrics"]
        timeline = result["timeline"]
        assert isinstance(metrics, dict)
        assert isinstance(timeline, list)
        self.assertEqual(metrics["unserved_energy_mj"], 0)
        self.assertEqual(timeline[-1]["battery_energy_mj"]["ups-a"], 408_000_000_000)

    def test_replay_and_semantic_hash_are_stable(self) -> None:
        scenario = parse_scenario(reference_scenario_data("healthy.scenario.json"), self.snapshot)
        first = simulate(self.snapshot, scenario)
        second = simulate(self.snapshot, scenario)
        self.assertEqual(first, second)
        semantic = {
            key: value for key, value in first.items() if key not in {"run_id", "computation_hash"}
        }
        self.assertEqual(first["computation_hash"], sha256_json(semantic))
        verification = verify_replay(self.snapshot, scenario, str(first["computation_hash"]))
        self.assertTrue(verification["matches"])

    def test_runtime_source_paralleling_is_rejected(self) -> None:
        data = reference_scenario_data("healthy.scenario.json")
        data["events"] = [
            {
                "id": "unsafe-transfer",
                "time_ms": 1,
                "kind": "atomic_transfer",
                "open_connection_ids": [],
                "close_connection_ids": ["generator-a-to-ats-a"],
            }
        ]
        scenario = parse_scenario(data, self.snapshot)
        with self.assertRaises(TopologyError):
            simulate(self.snapshot, scenario)

    def test_sub_millisecond_battery_milestone_fails_explicitly(self) -> None:
        snapshot_data = reference_snapshot_data()
        for component in snapshot_data["components"]:
            if component["id"] == "ups-a":
                component["usable_energy_mj"] += 1
        snapshot = parse_snapshot(snapshot_data)
        scenario_data = reference_scenario_data("healthy.scenario.json")
        scenario_data["snapshot_id"] = snapshot.snapshot_id
        scenario_data["events"] = [
            {
                "id": "fail-a",
                "time_ms": 0,
                "kind": "component_failure",
                "component_id": "utility-a",
                "status": "failed",
            }
        ]
        scenario = parse_scenario(scenario_data, snapshot)
        with self.assertRaisesRegex(ContractError, "millisecond"):
            simulate(snapshot, scenario)


class SinglePathReferenceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = parse_snapshot(reference_snapshot_data("reference-n.snapshot.json"))

    def test_utility_loss_matches_independent_calculation(self) -> None:
        scenario = parse_scenario(
            reference_scenario_data("n-utility-loss.scenario.json"), self.snapshot
        )
        result = simulate(self.snapshot, scenario)
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        self.assertEqual(metrics["demanded_energy_mj"], 600_000_000_000)
        self.assertEqual(metrics["served_energy_mj"], 480_000_000_000)
        self.assertEqual(metrics["unserved_energy_mj"], 120_000_000_000)
        self.assertEqual(metrics["service_ratio_ppm"], 800_000)
        self.assertEqual(metrics["interruption_duration_ms"], 120_000)
        self.assertEqual(metrics["interruption_count"], 1)
        self.assertEqual(metrics["modeled_redundancy_state"], "no_path")
        timeline = result["timeline"]
        assert isinstance(timeline, list)
        outage = [segment for segment in timeline if segment["unserved_w"] > 0]
        self.assertEqual(outage[0]["start_ms"], 300_000)
        self.assertEqual(outage[-1]["end_ms"], 420_000)
        self.assertEqual(timeline[-1]["battery_energy_mj"]["ups-n"], 0)
        alarms = result["alarms"]
        assert isinstance(alarms, list)
        alarm_times = {(alarm["code"], alarm["time_ms"]) for alarm in alarms}
        self.assertIn(("ups_low_energy", 264_000), alarm_times)
        self.assertIn(("ups_energy_depleted", 300_000), alarm_times)
        self.assertIn(("load_unserved", 300_000), alarm_times)


class ReserveUpsReferenceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = parse_snapshot(reference_snapshot_data("reference-n-plus-1.snapshot.json"))

    def test_absorbed_ups_failure_matches_independent_calculation(self) -> None:
        scenario = parse_scenario(
            reference_scenario_data("n-plus-1-ups-failure.scenario.json"), self.snapshot
        )
        result = simulate(self.snapshot, scenario)
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        self.assertEqual(metrics["unserved_energy_mj"], 0)
        self.assertEqual(metrics["service_ratio_ppm"], 1_000_000)
        self.assertEqual(metrics["interruption_count"], 0)
        self.assertEqual(metrics["minimum_served_w"], 1_600_000)
        self.assertEqual(metrics["modeled_redundancy_state"], "battery_backed")
        timeline = result["timeline"]
        assert isinstance(timeline, list)
        bridge = [
            segment for segment in timeline if segment["redundancy_state"] == "battery_backed"
        ]
        self.assertEqual(bridge[0]["start_ms"], 120_000)
        self.assertEqual(bridge[-1]["end_ms"], 150_000)
        final_energy = timeline[-1]["battery_energy_mj"]
        self.assertEqual(final_energy["ups-r1"], 432_000_000_000)
        self.assertEqual(final_energy["ups-r2"], 432_000_000_000)
        self.assertEqual(final_energy["ups-r3"], 408_000_000_000)


class GenericEngineTests(unittest.TestCase):
    def test_failure_and_restore_create_one_exact_interruption(self) -> None:
        snapshot = parse_snapshot(minimal_snapshot_data())
        scenario = parse_scenario(
            minimal_scenario_data(
                events=[
                    {
                        "id": "fail",
                        "time_ms": 100,
                        "kind": "component_failure",
                        "component_id": "source",
                        "status": "failed",
                    },
                    {
                        "id": "restore",
                        "time_ms": 300,
                        "kind": "component_restore",
                        "component_id": "source",
                        "status": "available",
                    },
                    {
                        "id": "step",
                        "time_ms": 500,
                        "kind": "load_step",
                        "component_id": "load",
                        "demand_w": 40,
                    },
                ]
            ),
            snapshot,
        )
        result = simulate(snapshot, scenario)
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        self.assertEqual(metrics["interruption_duration_ms"], 200)
        self.assertEqual(metrics["interruption_count"], 1)
        self.assertEqual(metrics["unserved_energy_mj"], 16_000)
        transitions = result["transitions"]
        assert isinstance(transitions, list)
        self.assertEqual([item["time_ms"] for item in transitions], [0, 100, 300, 500])

    def test_input_objects_are_not_mutated(self) -> None:
        snapshot_data = minimal_snapshot_data()
        scenario_data = minimal_scenario_data()
        original_snapshot = copy.deepcopy(snapshot_data)
        original_scenario = copy.deepcopy(scenario_data)
        snapshot = parse_snapshot(snapshot_data)
        scenario = parse_scenario(scenario_data, snapshot)
        simulate(snapshot, scenario)
        self.assertEqual(snapshot_data, original_snapshot)
        self.assertEqual(scenario_data, original_scenario)


if __name__ == "__main__":
    unittest.main()
