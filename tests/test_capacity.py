from __future__ import annotations

import unittest

from dc_twin.capacity import _edmonds_karp, initial_state, solve_capacity
from dc_twin.errors import InvariantError
from dc_twin.models import Availability
from dc_twin.validation import parse_snapshot
from tests.helpers import minimal_snapshot_data, reference_snapshot_data


class CapacityAllocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = parse_snapshot(reference_snapshot_data())

    def test_healthy_reference_is_balanced_and_deterministic(self) -> None:
        state = initial_state(self.snapshot)
        first = solve_capacity(self.snapshot, state)
        second = solve_capacity(self.snapshot, state.clone())
        self.assertEqual(first, second)
        self.assertEqual(first.demand_w, 1_600_000)
        self.assertEqual(first.served_w, 1_600_000)
        self.assertEqual(first.unserved_w, 0)
        self.assertEqual(first.source_power_w, {"utility-a": 800_000, "utility-b": 800_000})
        self.assertEqual(first.load_service_w, {"it-load-1": 800_000, "it-load-2": 800_000})
        self.assertEqual(first.redundancy_state, "two_n")

    def test_ups_becomes_a_source_only_when_upstream_is_unavailable(self) -> None:
        state = initial_state(self.snapshot)
        state.component_status["utility-a"] = Availability.FAILED
        summary = solve_capacity(self.snapshot, state)
        self.assertEqual(summary.served_w, 1_600_000)
        self.assertEqual(summary.source_power_w["ups-a"], 800_000)
        self.assertEqual(summary.source_power_w["utility-b"], 800_000)
        self.assertEqual(summary.battery_source_ids, ("ups-a",))

    def test_open_or_unavailable_path_never_carries_flow(self) -> None:
        state = initial_state(self.snapshot)
        state.component_status["pdu-b"] = Availability.MAINTENANCE
        summary = solve_capacity(self.snapshot, state)
        self.assertEqual(summary.served_w, 800_000)
        self.assertEqual(summary.unserved_w, 800_000)
        self.assertEqual(summary.redundancy_state, "partial_service")
        self.assertNotIn("ups-b-to-pdu-b", summary.connection_flow_w)

    def test_zero_demand_has_no_service_or_stranded_capacity(self) -> None:
        snapshot = parse_snapshot(minimal_snapshot_data())
        state = initial_state(snapshot)
        state.demand_w["load"] = 0
        summary = solve_capacity(snapshot, state)
        self.assertEqual(summary.demand_w, 0)
        self.assertEqual(summary.served_w, 0)
        self.assertEqual(summary.stranded_capacity_w, 0)
        self.assertEqual(summary.redundancy_state, "no_demand")

    def test_integral_max_flow_uses_residual_edges(self) -> None:
        capacities = {
            ("s", "a"): 3,
            ("s", "b"): 2,
            ("a", "b"): 2,
            ("a", "t"): 2,
            ("b", "t"): 3,
        }
        value, flows = _edmonds_karp(capacities, "s", "t")
        self.assertEqual(value, 5)
        self.assertEqual(flows[("s", "a")] + flows[("s", "b")], 5)

    def test_negative_capacity_is_rejected_as_an_invariant_violation(self) -> None:
        with self.assertRaisesRegex(InvariantError, "negative"):
            _edmonds_karp({("s", "t"): -1}, "s", "t")

    def test_unavailable_load_is_never_served(self) -> None:
        snapshot = parse_snapshot(minimal_snapshot_data())
        state = initial_state(snapshot)
        state.component_status["load"] = Availability.FAILED
        summary = solve_capacity(snapshot, state)
        self.assertEqual(summary.load_service_w["load"], 0)
        self.assertEqual(summary.served_w, 0)
        self.assertEqual(summary.unserved_w, 80)
        self.assertEqual(summary.redundancy_state, "no_path")

    def test_exhausted_source_starves_the_lower_priority_load(self) -> None:
        data = minimal_snapshot_data()
        data["components"].append(
            {
                "id": "load-2",
                "label": "Synthetic secondary load",
                "kind": "load",
                "path": "shared",
                "capacity_w": 100,
                "initial_status": "available",
                "demand_w": 40,
                "priority": 2,
                "service_order": 2,
            }
        )
        data["connections"].append(
            {
                "id": "bus-load-2",
                "from_component": "bus",
                "to_component": "load-2",
                "capacity_w": 100,
                "initial_closed": True,
            }
        )
        snapshot = parse_snapshot(data)
        state = initial_state(snapshot)
        state.demand_w["load"] = 100
        summary = solve_capacity(snapshot, state)
        self.assertEqual(summary.load_service_w, {"load": 100, "load-2": 0})
        self.assertEqual(summary.demand_w, 140)
        self.assertEqual(summary.served_w, 100)
        self.assertEqual(summary.unserved_w, 40)
        self.assertEqual(summary.stranded_capacity_w, 0)
        self.assertEqual(summary.redundancy_state, "partial_service")


if __name__ == "__main__":
    unittest.main()
