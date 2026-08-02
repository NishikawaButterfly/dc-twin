from __future__ import annotations

import copy
import unittest
from typing import Any

from dc_twin.errors import ContractError, DCTwinError, ResourceLimitError, TopologyError
from dc_twin.models import ComponentKind, EventKind
from dc_twin.validation import MAX_COMPONENTS, parse_scenario, parse_snapshot
from tests.helpers import minimal_scenario_data, minimal_snapshot_data, reference_snapshot_data


class SnapshotValidationTests(unittest.TestCase):
    def test_reference_snapshot_is_strict_and_typed(self) -> None:
        snapshot = parse_snapshot(reference_snapshot_data())
        self.assertEqual(snapshot.snapshot_id, "reference-2n")
        self.assertEqual(len(snapshot.components), 16)
        self.assertEqual(snapshot.component_by_id["ups-a"].usable_energy_mj, 432_000_000_000)
        self.assertIs(snapshot.component_by_id["it-load-1"].kind, ComponentKind.LOAD)

    def test_additional_reference_snapshots_are_strict_and_typed(self) -> None:
        single = parse_snapshot(reference_snapshot_data("reference-n.snapshot.json"))
        self.assertEqual(single.snapshot_id, "reference-n")
        self.assertEqual(len(single.components), 6)
        self.assertEqual(single.component_by_id["ups-n"].usable_energy_mj, 180_000_000_000)
        reserve = parse_snapshot(reference_snapshot_data("reference-n-plus-1.snapshot.json"))
        self.assertEqual(reserve.snapshot_id, "reference-n-plus-1")
        self.assertEqual(len(reserve.components), 9)
        self.assertEqual(reserve.component_by_id["ups-r3"].usable_energy_mj, 432_000_000_000)
        self.assertIs(reserve.component_by_id["ups-r3"].kind, ComponentKind.UPS)

    def test_unknown_fields_units_and_boolean_integers_are_rejected(self) -> None:
        cases = []
        unknown = minimal_snapshot_data()
        unknown["unexpected"] = True
        cases.append(unknown)
        units = minimal_snapshot_data()
        units["units"]["power"] = "kW"
        cases.append(units)
        boolean_capacity = minimal_snapshot_data()
        boolean_capacity["components"][0]["capacity_w"] = True
        cases.append(boolean_capacity)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ContractError):
                parse_snapshot(data)

    def test_duplicate_and_broken_references_are_rejected(self) -> None:
        duplicate = minimal_snapshot_data()
        duplicate["components"][1]["id"] = "source"
        with self.assertRaises(ContractError):
            parse_snapshot(duplicate)
        broken = minimal_snapshot_data()
        broken["connections"][0]["to_component"] = "missing"
        with self.assertRaises(TopologyError):
            parse_snapshot(broken)
        broken_group = minimal_snapshot_data()
        broken_group["redundancy_groups"][0]["members"] = ["missing"]
        with self.assertRaises(TopologyError):
            parse_snapshot(broken_group)

    def test_cycles_self_connections_and_load_outputs_are_rejected(self) -> None:
        self_connection = minimal_snapshot_data()
        self_connection["connections"][0]["to_component"] = "source"
        with self.assertRaises(TopologyError):
            parse_snapshot(self_connection)
        cycle = minimal_snapshot_data()
        cycle["connections"].append(
            {
                "id": "load-source",
                "from_component": "load",
                "to_component": "source",
                "capacity_w": 10,
                "initial_closed": True,
            }
        )
        with self.assertRaises(TopologyError):
            parse_snapshot(cycle)

    def test_parallel_ats_inputs_are_rejected(self) -> None:
        data = minimal_snapshot_data()
        data["components"].insert(
            1,
            {
                "id": "source-b",
                "label": "Synthetic source B",
                "kind": "utility",
                "path": "B",
                "capacity_w": 100,
                "initial_status": "available",
            },
        )
        data["components"][2]["kind"] = "ats"
        data["connections"].append(
            {
                "id": "source-b-bus",
                "from_component": "source-b",
                "to_component": "bus",
                "capacity_w": 100,
                "initial_closed": True,
            }
        )
        with self.assertRaisesRegex(TopologyError, "paralleling"):
            parse_snapshot(data)

    def test_component_resource_limit_is_enforced(self) -> None:
        data = minimal_snapshot_data()
        template = data["components"][1]
        data["components"] = [
            {**copy.deepcopy(template), "id": f"bus-{index}"} for index in range(MAX_COMPONENTS + 1)
        ]
        with self.assertRaises(ResourceLimitError):
            parse_snapshot(data)

    def test_snapshot_contract_violations_report_stable_codes(self) -> None:
        def with_cycle(data: dict[str, Any]) -> None:
            data["components"].insert(
                2,
                {
                    "id": "bus-2",
                    "label": "Synthetic second bus",
                    "kind": "switchgear",
                    "path": "A",
                    "capacity_w": 100,
                    "initial_status": "available",
                },
            )
            data["connections"].extend(
                [
                    {
                        "id": "bus-bus-2",
                        "from_component": "bus",
                        "to_component": "bus-2",
                        "capacity_w": 100,
                        "initial_closed": True,
                    },
                    {
                        "id": "bus-2-bus",
                        "from_component": "bus-2",
                        "to_component": "bus",
                        "capacity_w": 100,
                        "initial_closed": True,
                    },
                ]
            )

        def set_item(path: tuple[Any, ...], value: Any) -> Any:
            def apply(data: dict[str, Any]) -> None:
                target: Any = data
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

            return apply

        cases: list[tuple[str, str, Any]] = [
            ("missing_field", "contract.invalid_field", lambda d: d.pop("units")),
            ("schema_id", "contract.invalid_field", set_item(("schema_id",), "wrong")),
            ("schema_version", "contract.invalid_field", set_item(("schema_version",), "2.0.0")),
            (
                "classification",
                "contract.invalid_field",
                set_item(("data_classification",), "internal"),
            ),
            (
                "overlong_string",
                "contract.invalid_field",
                set_item(("provenance", "title"), "x" * 241),
            ),
            (
                "control_characters",
                "contract.invalid_field",
                set_item(("components", 0, "label"), "bad\x00label"),
            ),
            ("bad_identifier", "contract.invalid_field", set_item(("snapshot_id",), "bad id!")),
            ("bad_revision", "contract.invalid_field", set_item(("design_revision",), "rev:1")),
            (
                "unknown_kind",
                "contract.invalid_field",
                set_item(("components", 0, "kind"), "flux-capacitor"),
            ),
            ("bad_path", "contract.invalid_field", set_item(("components", 0, "path"), "C")),
            (
                "non_boolean_closed",
                "contract.invalid_field",
                set_item(("connections", 0, "initial_closed"), 1),
            ),
            (
                "assumptions_not_list",
                "contract.invalid_field",
                set_item(("assumptions",), "text"),
            ),
            (
                "duplicate_assumptions",
                "contract.invalid_field",
                set_item(("assumptions",), ["Same.", "Same."]),
            ),
            ("components_not_list", "contract.invalid_field", set_item(("components",), {})),
            ("no_connections", "contract.connection_limit", set_item(("connections",), [])),
            (
                "too_many_groups",
                "contract.invalid_field",
                set_item(
                    ("redundancy_groups",),
                    [
                        {"id": f"g-{index}", "mode": "N", "members": ["source"]}
                        for index in range(101)
                    ],
                ),
            ),
            (
                "bad_group_mode",
                "contract.invalid_field",
                set_item(("redundancy_groups", 0, "mode"), "THREE_N"),
            ),
            (
                "empty_group_members",
                "contract.invalid_field",
                set_item(("redundancy_groups", 0, "members"), []),
            ),
            (
                "group_members_not_list",
                "contract.invalid_field",
                set_item(("redundancy_groups", 0, "members"), "source"),
            ),
            (
                "duplicate_group_members",
                "contract.invalid_field",
                set_item(("redundancy_groups", 0, "members"), ["source", "source"]),
            ),
            (
                "broken_source_reference",
                "topology.broken_reference",
                set_item(("connections", 0, "from_component"), "missing"),
            ),
            ("cycle", "topology.cycle_not_supported", with_cycle),
        ]
        for label, expected_code, mutate in cases:
            data = minimal_snapshot_data()
            mutate(data)
            with self.subTest(case=label):
                with self.assertRaises(DCTwinError) as context:
                    parse_snapshot(data)
                self.assertEqual(context.exception.code, expected_code)
        with self.assertRaises(ContractError) as root_context:
            parse_snapshot([])
        self.assertEqual(root_context.exception.code, "contract.invalid_field")


class ScenarioValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = parse_snapshot(minimal_snapshot_data())

    def test_sorts_equal_time_events_by_semantic_priority(self) -> None:
        data = minimal_scenario_data(
            events=[
                {
                    "id": "restore",
                    "time_ms": 10,
                    "kind": "component_restore",
                    "component_id": "source",
                    "status": "available",
                },
                {
                    "id": "fail",
                    "time_ms": 5,
                    "kind": "component_failure",
                    "component_id": "source",
                    "status": "failed",
                },
            ]
        )
        scenario = parse_scenario(data, self.snapshot)
        self.assertEqual(
            [event.kind for event in scenario.events],
            [EventKind.COMPONENT_FAILURE, EventKind.COMPONENT_RESTORE],
        )

    def test_snapshot_mismatch_and_out_of_horizon_are_rejected(self) -> None:
        mismatch = minimal_scenario_data()
        mismatch["snapshot_id"] = "another"
        with self.assertRaises(ContractError):
            parse_scenario(mismatch, self.snapshot)
        outside = minimal_scenario_data(
            events=[
                {
                    "id": "late",
                    "time_ms": 1001,
                    "kind": "component_failure",
                    "component_id": "source",
                    "status": "failed",
                }
            ]
        )
        with self.assertRaises(ContractError):
            parse_scenario(outside, self.snapshot)

    def test_contradictory_unknown_and_invalid_target_events_are_rejected(self) -> None:
        contradictory = minimal_scenario_data(
            events=[
                {
                    "id": "a",
                    "time_ms": 10,
                    "kind": "component_failure",
                    "component_id": "source",
                    "status": "failed",
                },
                {
                    "id": "b",
                    "time_ms": 10,
                    "kind": "component_restore",
                    "component_id": "source",
                    "status": "available",
                },
            ]
        )
        with self.assertRaises(TopologyError):
            parse_scenario(contradictory, self.snapshot)
        unknown = minimal_scenario_data(
            events=[
                {
                    "id": "a",
                    "time_ms": 10,
                    "kind": "component_failure",
                    "component_id": "missing",
                    "status": "failed",
                }
            ]
        )
        with self.assertRaises(TopologyError):
            parse_scenario(unknown, self.snapshot)
        wrong_target = minimal_scenario_data(
            events=[
                {
                    "id": "a",
                    "time_ms": 10,
                    "kind": "generator_running",
                    "component_id": "source",
                    "status": "available",
                }
            ]
        )
        with self.assertRaises(TopologyError):
            parse_scenario(wrong_target, self.snapshot)

    def test_atomic_transfer_and_load_step_are_strict(self) -> None:
        overlap = minimal_scenario_data(
            events=[
                {
                    "id": "transfer",
                    "time_ms": 10,
                    "kind": "atomic_transfer",
                    "open_connection_ids": ["bus-load"],
                    "close_connection_ids": ["bus-load"],
                }
            ]
        )
        with self.assertRaises(ContractError):
            parse_scenario(overlap, self.snapshot)
        excessive_load = minimal_scenario_data(
            events=[
                {
                    "id": "step",
                    "time_ms": 10,
                    "kind": "load_step",
                    "component_id": "load",
                    "demand_w": 101,
                }
            ]
        )
        with self.assertRaises(TopologyError):
            parse_scenario(excessive_load, self.snapshot)

    def test_scenario_contract_violations_report_stable_codes(self) -> None:
        cases: list[tuple[str, str, dict[str, Any]]] = [
            ("schema_id", "contract.invalid_field", {"schema_id": "wrong"}),
            ("schema_version", "contract.invalid_field", {"schema_version": "2.0.0"}),
            ("classification", "contract.invalid_field", {"data_classification": "internal"}),
            ("events_not_list", "contract.invalid_field", {"events": {}}),
            ("event_limit", "contract.event_limit", {"events": [{}] * 1_001}),
            (
                "timeline_limit",
                "contract.timeline_limit",
                {"horizon_ms": 1_000_000, "resolution_ms": 1},
            ),
        ]
        for label, expected_code, overrides in cases:
            data = minimal_scenario_data()
            data.update(overrides)
            with self.subTest(case=label):
                with self.assertRaises(DCTwinError) as context:
                    parse_scenario(data, self.snapshot)
                self.assertEqual(context.exception.code, expected_code)

    def test_invalid_event_shapes_report_stable_codes(self) -> None:
        cases: list[tuple[str, str, dict[str, Any]]] = [
            (
                "empty_transfer",
                "contract.invalid_field",
                {
                    "id": "transfer",
                    "time_ms": 10,
                    "kind": "atomic_transfer",
                    "open_connection_ids": [],
                    "close_connection_ids": [],
                },
            ),
            (
                "status_kind_mismatch",
                "contract.invalid_field",
                {
                    "id": "failure",
                    "time_ms": 10,
                    "kind": "component_failure",
                    "component_id": "source",
                    "status": "available",
                },
            ),
            (
                "load_step_on_non_load",
                "scenario.invalid_target",
                {
                    "id": "step",
                    "time_ms": 10,
                    "kind": "load_step",
                    "component_id": "bus",
                    "demand_w": 10,
                },
            ),
            (
                "unknown_connection",
                "scenario.unknown_connection",
                {
                    "id": "transfer",
                    "time_ms": 10,
                    "kind": "atomic_transfer",
                    "open_connection_ids": [],
                    "close_connection_ids": ["missing"],
                },
            ),
        ]
        for label, expected_code, event in cases:
            data = minimal_scenario_data(events=[event])
            with self.subTest(case=label):
                with self.assertRaises(DCTwinError) as context:
                    parse_scenario(data, self.snapshot)
                self.assertEqual(context.exception.code, expected_code)

    def test_generator_outcome_requires_source_loss_and_declared_delay(self) -> None:
        snapshot_data = minimal_snapshot_data()
        snapshot_data["components"].insert(
            1,
            {
                "id": "generator",
                "label": "Synthetic generator",
                "kind": "generator",
                "path": "A",
                "capacity_w": 100,
                "initial_status": "available",
                "start_delay_ms": 50,
            },
        )
        snapshot = parse_snapshot(snapshot_data)
        no_loss = minimal_scenario_data(
            events=[
                {
                    "id": "running",
                    "time_ms": 50,
                    "kind": "generator_running",
                    "component_id": "generator",
                    "status": "available",
                }
            ]
        )
        with self.assertRaisesRegex(TopologyError, "preceding"):
            parse_scenario(no_loss, snapshot)
        too_early = minimal_scenario_data(
            events=[
                {
                    "id": "failure",
                    "time_ms": 10,
                    "kind": "component_failure",
                    "component_id": "source",
                    "status": "failed",
                },
                {
                    "id": "running",
                    "time_ms": 59,
                    "kind": "generator_running",
                    "component_id": "generator",
                    "status": "available",
                },
            ]
        )
        with self.assertRaisesRegex(TopologyError, "start delay"):
            parse_scenario(too_early, snapshot)


if __name__ == "__main__":
    unittest.main()
