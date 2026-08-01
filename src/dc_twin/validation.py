"""Strict contract and topology validation with bounded resource use."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from enum import Enum
from typing import Any, cast

from dc_twin.canonical import sha256_json
from dc_twin.errors import ContractError, InvalidParameter, ResourceLimitError, TopologyError
from dc_twin.models import (
    Availability,
    Component,
    ComponentKind,
    Connection,
    Event,
    EventKind,
    RedundancyGroup,
    Scenario,
    Snapshot,
)

MAX_COMPONENTS = 250
MAX_CONNECTIONS = 500
MAX_EVENTS = 1_000
MAX_HORIZON_MS = 7 * 24 * 60 * 60 * 1_000
MAX_TRANSITIONS = 10_000
MAX_TIMELINE_SEGMENTS = 10_000
MAX_TELEMETRY_POINTS = 250_000
MAX_ASSUMPTIONS = 50
MAX_REDUNDANCY_GROUPS = 100
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
DESIGN_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_FIRST_PRINTABLE_ORDINAL = 32


def _fail(path: str, reason: str, *, code: str = "contract.invalid_field") -> ContractError:
    return ContractError(
        code,
        f"Invalid value at {path}: {reason}",
        invalid_params=(InvalidParameter(name=path, reason=reason),),
    )


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise _fail(path, "must be a JSON object")
    return dict(cast(Mapping[str, Any], value))


def _strict_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: AbstractSet[str] = frozenset(),
    path: str,
) -> None:
    missing = sorted(required - value.keys())
    unexpected = sorted(value.keys() - required - optional)
    if missing:
        raise _fail(path, f"missing required fields: {', '.join(missing)}")
    if unexpected:
        raise _fail(path, f"unexpected fields: {', '.join(unexpected)}")


def _string(value: Any, path: str, *, max_length: int = 120) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise _fail(path, f"must be a non-empty string no longer than {max_length} characters")
    if any(ord(character) < _FIRST_PRINTABLE_ORDINAL for character in value):
        raise _fail(path, "must not contain control characters")
    return value


def _identifier(value: Any, path: str) -> str:
    candidate = _string(value, path, max_length=64)
    if not IDENTIFIER.fullmatch(candidate):
        raise _fail(path, "must match the stable identifier syntax")
    return candidate


def _design_revision(value: Any, path: str) -> str:
    candidate = _string(value, path, max_length=64)
    if not DESIGN_REVISION.fullmatch(candidate):
        raise _fail(path, "must use letters, digits, periods, underscores, or hyphens")
    return candidate


def _integer(
    value: Any,
    path: str,
    *,
    minimum: int = 0,
    maximum: int = 10**15,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _fail(path, f"must be an integer from {minimum} through {maximum}")
    return value


def _enum[T: Enum](enum_type: type[T], value: Any, path: str) -> T:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise _fail(path, f"unsupported value {value!r}") from exc


def _string_list(value: Any, path: str, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise _fail(path, f"must be an array with at most {maximum} items")
    result = tuple(_identifier(item, f"{path}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise _fail(path, "must not contain duplicate identifiers")
    return result


def parse_snapshot(value: Any) -> Snapshot:
    """Parse and validate ElectricalDesignSnapshot v1."""

    data = _object(value, "$")
    _strict_keys(
        data,
        required={
            "schema_id",
            "schema_version",
            "snapshot_id",
            "design_revision",
            "data_classification",
            "provenance",
            "units",
            "assumptions",
            "components",
            "connections",
            "redundancy_groups",
        },
        path="$",
    )
    if data["schema_id"] != "dc-twin.electrical-design-snapshot":
        raise _fail("$.schema_id", "unsupported schema identifier")
    if data["schema_version"] != "1.0.0":
        raise _fail("$.schema_version", "only version 1.0.0 is supported")
    if data["data_classification"] != "synthetic":
        raise _fail("$.data_classification", "public fixtures must be classified synthetic")

    provenance_data = _object(data["provenance"], "$.provenance")
    _strict_keys(
        provenance_data,
        required={"title", "created_by", "method"},
        path="$.provenance",
    )
    provenance = {
        key: _string(provenance_data[key], f"$.provenance.{key}", max_length=240)
        for key in sorted(provenance_data)
    }

    units_data = _object(data["units"], "$.units")
    _strict_keys(units_data, required={"power", "energy", "time"}, path="$.units")
    units = {key: _string(units_data[key], f"$.units.{key}") for key in sorted(units_data)}
    if units != {"energy": "mJ", "power": "W", "time": "ms"}:
        raise _fail("$.units", "v1 requires W, mJ, and ms exactly")

    assumptions_raw = data["assumptions"]
    if not isinstance(assumptions_raw, list) or len(assumptions_raw) > MAX_ASSUMPTIONS:
        raise _fail("$.assumptions", f"must be an array with at most {MAX_ASSUMPTIONS} items")
    assumptions = tuple(
        _string(item, f"$.assumptions[{index}]", max_length=500)
        for index, item in enumerate(assumptions_raw)
    )
    if len(set(assumptions)) != len(assumptions):
        raise _fail("$.assumptions", "must not contain duplicate statements")

    components_raw = data["components"]
    if not isinstance(components_raw, list):
        raise _fail("$.components", "must be an array")
    if not components_raw or len(components_raw) > MAX_COMPONENTS:
        raise ResourceLimitError(
            "contract.component_limit",
            f"A snapshot must contain 1 through {MAX_COMPONENTS} components.",
        )
    components = tuple(
        _parse_component(item, f"$.components[{index}]")
        for index, item in enumerate(components_raw)
    )
    _ensure_unique((component.id for component in components), "$.components", "component IDs")

    connections_raw = data["connections"]
    if (
        not isinstance(connections_raw, list)
        or not connections_raw
        or len(connections_raw) > MAX_CONNECTIONS
    ):
        raise ResourceLimitError(
            "contract.connection_limit",
            f"A snapshot must contain 1 through {MAX_CONNECTIONS} connections.",
        )
    connections = tuple(
        _parse_connection(item, f"$.connections[{index}]")
        for index, item in enumerate(connections_raw)
    )
    _ensure_unique((connection.id for connection in connections), "$.connections", "connection IDs")

    groups_raw = data["redundancy_groups"]
    if not isinstance(groups_raw, list) or len(groups_raw) > MAX_REDUNDANCY_GROUPS:
        raise _fail(
            "$.redundancy_groups", f"must be an array with at most {MAX_REDUNDANCY_GROUPS} items"
        )
    groups = tuple(
        _parse_redundancy_group(item, f"$.redundancy_groups[{index}]")
        for index, item in enumerate(groups_raw)
    )
    _ensure_unique((group.id for group in groups), "$.redundancy_groups", "group IDs")

    snapshot = Snapshot(
        schema_id="dc-twin.electrical-design-snapshot",
        schema_version="1.0.0",
        snapshot_id=_identifier(data["snapshot_id"], "$.snapshot_id"),
        design_revision=_design_revision(data["design_revision"], "$.design_revision"),
        data_classification="synthetic",
        provenance=provenance,
        units=units,
        assumptions=assumptions,
        components=components,
        connections=connections,
        redundancy_groups=groups,
        source_hash=sha256_json(data),
    )
    validate_topology(snapshot)
    return snapshot


def _parse_component(value: Any, path: str) -> Component:
    data = _object(value, path)
    base = {"id", "label", "kind", "path", "capacity_w", "initial_status"}
    kind = _enum(ComponentKind, data.get("kind"), f"{path}.kind")
    optional: set[str] = set()
    required = set(base)
    if kind is ComponentKind.LOAD:
        required.update({"demand_w", "priority", "service_order"})
    elif kind is ComponentKind.UPS:
        required.update({"usable_energy_mj", "low_energy_threshold_pct"})
    elif kind is ComponentKind.GENERATOR:
        required.add("start_delay_ms")
    _strict_keys(data, required=required, optional=optional, path=path)
    path_name = data["path"]
    if path_name not in {"A", "B", "shared"}:
        raise _fail(f"{path}.path", "must be A, B, or shared")
    capacity = _integer(data["capacity_w"], f"{path}.capacity_w", minimum=1, maximum=10**10)
    demand_w: int | None = None
    priority: int | None = None
    service_order: int | None = None
    energy_mj: int | None = None
    threshold: int | None = None
    delay_ms: int | None = None
    if kind is ComponentKind.LOAD:
        demand_w = _integer(data["demand_w"], f"{path}.demand_w", minimum=0, maximum=10**10)
        priority = _integer(data["priority"], f"{path}.priority", minimum=1, maximum=100)
        service_order = _integer(
            data["service_order"], f"{path}.service_order", minimum=1, maximum=10_000
        )
    elif kind is ComponentKind.UPS:
        energy_mj = _integer(
            data["usable_energy_mj"],
            f"{path}.usable_energy_mj",
            minimum=1,
            maximum=10**18,
        )
        threshold = _integer(
            data["low_energy_threshold_pct"],
            f"{path}.low_energy_threshold_pct",
            minimum=1,
            maximum=99,
        )
    elif kind is ComponentKind.GENERATOR:
        delay_ms = _integer(
            data["start_delay_ms"], f"{path}.start_delay_ms", minimum=0, maximum=3_600_000
        )
    return Component(
        id=_identifier(data["id"], f"{path}.id"),
        label=_string(data["label"], f"{path}.label"),
        kind=kind,
        path=cast(str, path_name),
        capacity_w=capacity,
        initial_status=_enum(Availability, data["initial_status"], f"{path}.initial_status"),
        demand_w=demand_w,
        priority=priority,
        service_order=service_order,
        usable_energy_mj=energy_mj,
        low_energy_threshold_pct=threshold,
        start_delay_ms=delay_ms,
    )


def _parse_connection(value: Any, path: str) -> Connection:
    data = _object(value, path)
    _strict_keys(
        data,
        required={"id", "from_component", "to_component", "capacity_w", "initial_closed"},
        path=path,
    )
    initial_closed = data["initial_closed"]
    if type(initial_closed) is not bool:
        raise _fail(f"{path}.initial_closed", "must be a boolean")
    return Connection(
        id=_identifier(data["id"], f"{path}.id"),
        from_component=_identifier(data["from_component"], f"{path}.from_component"),
        to_component=_identifier(data["to_component"], f"{path}.to_component"),
        capacity_w=_integer(data["capacity_w"], f"{path}.capacity_w", minimum=1, maximum=10**10),
        initial_closed=initial_closed,
    )


def _parse_redundancy_group(value: Any, path: str) -> RedundancyGroup:
    data = _object(value, path)
    _strict_keys(data, required={"id", "mode", "members"}, path=path)
    if data["mode"] not in {"N", "N_PLUS_1", "TWO_N"}:
        raise _fail(f"{path}.mode", "must be N, N_PLUS_1, or TWO_N")
    members = _string_list(data["members"], f"{path}.members", maximum=MAX_COMPONENTS)
    if not members:
        raise _fail(f"{path}.members", "must contain at least one component")
    return RedundancyGroup(
        id=_identifier(data["id"], f"{path}.id"),
        mode=cast(str, data["mode"]),
        members=members,
    )


def _ensure_unique(values: Any, path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise _fail(path, f"duplicate {label}: {value}")
        seen.add(value)


def validate_topology(snapshot: Snapshot) -> None:
    """Reject broken, cyclic, ambiguous, or source-paralleling v1 graphs."""

    components = snapshot.component_by_id
    incoming: dict[str, list[Connection]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for connection in snapshot.connections:
        if connection.from_component not in components:
            raise TopologyError(
                "topology.broken_reference",
                f"Connection {connection.id} references unknown source "
                f"{connection.from_component}.",
            )
        if connection.to_component not in components:
            raise TopologyError(
                "topology.broken_reference",
                f"Connection {connection.id} references unknown target {connection.to_component}.",
            )
        if connection.from_component == connection.to_component:
            raise TopologyError(
                "topology.self_connection", f"Connection {connection.id} is self-referential."
            )
        incoming[connection.to_component].append(connection)
        outgoing[connection.from_component].append(connection.to_component)
    for component in snapshot.components:
        if component.kind in {ComponentKind.ATS, ComponentKind.STS}:
            closed_inputs = sum(item.initial_closed for item in incoming[component.id])
            if closed_inputs > 1:
                raise TopologyError(
                    "topology.parallel_sources",
                    f"{component.id} has more than one initially closed input; "
                    "v1 forbids paralleling.",
                )
        if component.kind is ComponentKind.LOAD and outgoing[component.id]:
            raise TopologyError(
                "topology.load_not_terminal", f"Load {component.id} must be a terminal node."
            )
    for group in snapshot.redundancy_groups:
        missing = sorted(set(group.members) - components.keys())
        if missing:
            raise TopologyError(
                "topology.broken_redundancy_group",
                f"Redundancy group {group.id} references unknown members: {', '.join(missing)}.",
            )
    _reject_cycles(components, outgoing)


def _reject_cycles(components: Mapping[str, Component], outgoing: Mapping[str, list[str]]) -> None:
    color = dict.fromkeys(components, 0)

    def visit(component_id: str) -> None:
        color[component_id] = 1
        for target in sorted(outgoing.get(component_id, [])):
            if color[target] == 1:
                raise TopologyError(
                    "topology.cycle_not_supported",
                    f"Directed cycle detected at {target}; v1 supports DAG topologies only.",
                )
            if color[target] == 0:
                visit(target)
        color[component_id] = 2

    for component_id in sorted(components):
        if color[component_id] == 0:
            visit(component_id)


def parse_scenario(value: Any, snapshot: Snapshot) -> Scenario:
    """Parse a bounded scenario and validate all references before simulation."""

    data = _object(value, "$")
    _strict_keys(
        data,
        required={
            "schema_id",
            "schema_version",
            "scenario_id",
            "label",
            "snapshot_id",
            "horizon_ms",
            "resolution_ms",
            "data_classification",
            "events",
        },
        path="$",
    )
    if data["schema_id"] != "dc-twin.scenario":
        raise _fail("$.schema_id", "unsupported schema identifier")
    if data["schema_version"] != "1.0.0":
        raise _fail("$.schema_version", "only version 1.0.0 is supported")
    if data["snapshot_id"] != snapshot.snapshot_id:
        raise _fail("$.snapshot_id", "does not match the supplied design snapshot")
    if data["data_classification"] != "synthetic":
        raise _fail("$.data_classification", "public scenarios must be classified synthetic")
    horizon_ms = _integer(data["horizon_ms"], "$.horizon_ms", minimum=1, maximum=MAX_HORIZON_MS)
    resolution_ms = _integer(
        data["resolution_ms"], "$.resolution_ms", minimum=1, maximum=horizon_ms
    )
    events_raw = data["events"]
    if not isinstance(events_raw, list):
        raise _fail("$.events", "must be an array")
    if len(events_raw) > MAX_EVENTS:
        raise ResourceLimitError(
            "contract.event_limit", f"A scenario supports at most {MAX_EVENTS} external events."
        )
    resolution_segments = (horizon_ms + resolution_ms - 1) // resolution_ms
    estimated_segments = (
        resolution_segments
        + len(events_raw)
        + 2 * sum(component.kind is ComponentKind.UPS for component in snapshot.components)
    )
    if estimated_segments > MAX_TIMELINE_SEGMENTS:
        raise ResourceLimitError(
            "contract.timeline_limit",
            f"Scenario would exceed {MAX_TIMELINE_SEGMENTS} timeline segments.",
        )
    points_per_segment = (
        4
        + sum(component.kind is ComponentKind.UPS for component in snapshot.components)
        + sum(component.kind is ComponentKind.LOAD for component in snapshot.components)
        + sum(
            component.kind in {ComponentKind.UTILITY, ComponentKind.GENERATOR}
            for component in snapshot.components
        )
    )
    if estimated_segments * points_per_segment > MAX_TELEMETRY_POINTS:
        raise ResourceLimitError(
            "contract.telemetry_limit",
            f"Scenario would exceed {MAX_TELEMETRY_POINTS} synthetic telemetry points.",
        )
    events = tuple(
        _parse_event(item, f"$.events[{index}]", horizon_ms=horizon_ms)
        for index, item in enumerate(events_raw)
    )
    _ensure_unique((event.id for event in events), "$.events", "event IDs")
    _validate_event_references(events, snapshot)
    _validate_generator_timing(events, snapshot)
    events = tuple(sorted(events, key=lambda item: (item.time_ms, item.semantic_priority, item.id)))
    return Scenario(
        schema_id="dc-twin.scenario",
        schema_version="1.0.0",
        scenario_id=_identifier(data["scenario_id"], "$.scenario_id"),
        label=_string(data["label"], "$.label", max_length=160),
        snapshot_id=snapshot.snapshot_id,
        horizon_ms=horizon_ms,
        resolution_ms=resolution_ms,
        data_classification="synthetic",
        events=events,
        source_hash=sha256_json(data),
    )


def _parse_event(value: Any, path: str, *, horizon_ms: int) -> Event:
    data = _object(value, path)
    base = {"id", "time_ms", "kind"}
    kind = _enum(EventKind, data.get("kind"), f"{path}.kind")
    if kind is EventKind.ATOMIC_TRANSFER:
        required = base | {"open_connection_ids", "close_connection_ids"}
    elif kind is EventKind.LOAD_STEP:
        required = base | {"component_id", "demand_w"}
    else:
        required = base | {"component_id", "status"}
    _strict_keys(data, required=required, path=path)
    time_ms = _integer(data["time_ms"], f"{path}.time_ms", maximum=horizon_ms)
    component_id: str | None = None
    status: Availability | None = None
    open_ids: tuple[str, ...] = ()
    close_ids: tuple[str, ...] = ()
    demand_w: int | None = None
    if kind is EventKind.ATOMIC_TRANSFER:
        open_ids = _string_list(
            data["open_connection_ids"], f"{path}.open_connection_ids", maximum=MAX_CONNECTIONS
        )
        close_ids = _string_list(
            data["close_connection_ids"], f"{path}.close_connection_ids", maximum=MAX_CONNECTIONS
        )
        if not open_ids and not close_ids:
            raise _fail(path, "an atomic transfer must open or close at least one connection")
        overlap = sorted(set(open_ids) & set(close_ids))
        if overlap:
            raise _fail(path, f"cannot open and close the same connection: {', '.join(overlap)}")
    else:
        component_id = _identifier(data["component_id"], f"{path}.component_id")
        if kind is EventKind.LOAD_STEP:
            demand_w = _integer(data["demand_w"], f"{path}.demand_w", minimum=0, maximum=10**10)
        else:
            status = _enum(Availability, data["status"], f"{path}.status")
            expected_status = {
                EventKind.COMPONENT_FAILURE: Availability.FAILED,
                EventKind.COMPONENT_RESTORE: Availability.AVAILABLE,
                EventKind.MAINTENANCE_START: Availability.MAINTENANCE,
                EventKind.MAINTENANCE_END: Availability.AVAILABLE,
                EventKind.GENERATOR_RUNNING: Availability.AVAILABLE,
                EventKind.GENERATOR_START_FAILURE: Availability.FAILED,
            }[kind]
            if status is not expected_status:
                raise _fail(f"{path}.status", f"must be {expected_status.value} for {kind.value}")
    return Event(
        id=_identifier(data["id"], f"{path}.id"),
        time_ms=time_ms,
        kind=kind,
        component_id=component_id,
        status=status,
        open_connection_ids=open_ids,
        close_connection_ids=close_ids,
        demand_w=demand_w,
    )


def _validate_event_references(events: tuple[Event, ...], snapshot: Snapshot) -> None:
    components = snapshot.component_by_id
    connections = snapshot.connection_by_id
    component_events: set[tuple[int, str]] = set()
    for event in events:
        if event.component_id is not None:
            component = components.get(event.component_id)
            if component is None:
                raise TopologyError(
                    "scenario.unknown_component",
                    f"Event {event.id} references unknown component {event.component_id}.",
                )
            key = (event.time_ms, event.component_id)
            if key in component_events:
                raise TopologyError(
                    "scenario.contradictory_events",
                    f"Multiple events target {event.component_id} at {event.time_ms} ms.",
                )
            component_events.add(key)
            if (
                event.kind
                in {
                    EventKind.GENERATOR_RUNNING,
                    EventKind.GENERATOR_START_FAILURE,
                }
                and component.kind is not ComponentKind.GENERATOR
            ):
                raise TopologyError(
                    "scenario.invalid_target",
                    f"Event {event.id} requires a generator target.",
                )
            if event.kind is EventKind.LOAD_STEP:
                if component.kind is not ComponentKind.LOAD:
                    raise TopologyError(
                        "scenario.invalid_target", f"Event {event.id} requires a load target."
                    )
                if event.demand_w is not None and event.demand_w > component.capacity_w:
                    raise TopologyError(
                        "scenario.load_above_rating",
                        f"Event {event.id} sets demand above {component.id}'s rating.",
                    )
        for connection_id in (*event.open_connection_ids, *event.close_connection_ids):
            if connection_id not in connections:
                raise TopologyError(
                    "scenario.unknown_connection",
                    f"Event {event.id} references unknown connection {connection_id}.",
                )


def _validate_generator_timing(events: tuple[Event, ...], snapshot: Snapshot) -> None:
    """Require generator outcomes to respect the declared delay after same-path utility loss."""

    components = snapshot.component_by_id
    ordered = sorted(events, key=lambda item: (item.time_ms, item.semantic_priority, item.id))
    for event in ordered:
        if event.kind not in {
            EventKind.GENERATOR_RUNNING,
            EventKind.GENERATOR_START_FAILURE,
        }:
            continue
        if event.component_id is None:
            raise TopologyError(
                "scenario.invalid_target", f"Event {event.id} has no generator target."
            )
        generator = components[event.component_id]
        source_losses = [
            candidate
            for candidate in ordered
            if candidate.kind is EventKind.COMPONENT_FAILURE
            and candidate.time_ms <= event.time_ms
            and candidate.component_id is not None
            and components[candidate.component_id].kind is ComponentKind.UTILITY
            and components[candidate.component_id].path == generator.path
        ]
        if not source_losses:
            raise TopologyError(
                "scenario.generator_without_source_loss",
                f"Event {event.id} has no preceding same-path utility failure in v1.",
            )
        source_loss = max(source_losses, key=lambda item: (item.time_ms, item.id))
        elapsed_ms = event.time_ms - source_loss.time_ms
        start_delay_ms = generator.start_delay_ms or 0
        if elapsed_ms < start_delay_ms:
            raise TopologyError(
                "scenario.generator_start_too_early",
                f"Event {event.id} occurs after {elapsed_ms} ms, "
                f"below {generator.id}'s {start_delay_ms} ms start delay.",
            )
