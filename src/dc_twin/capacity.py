"""Deterministic integral capacity allocation for the v1 directed-DAG model."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from dc_twin.errors import InvariantError
from dc_twin.models import Availability, ComponentKind, RuntimeState, Snapshot

type Node = str
type Edge = tuple[Node, Node]

_TWO_N_PATH_COUNT = 2


@dataclass(frozen=True, slots=True)
class CapacityFlowSummary:
    """One instantaneous, lossless active-power allocation."""

    demand_w: int
    served_w: int
    unserved_w: int
    stranded_capacity_w: int
    redundancy_state: str
    load_service_w: dict[str, int]
    connection_flow_w: dict[str, int]
    component_flow_w: dict[str, int]
    source_power_w: dict[str, int]
    battery_source_ids: tuple[str, ...]


def initial_state(snapshot: Snapshot) -> RuntimeState:
    """Build isolated runtime state from immutable design input."""

    return RuntimeState(
        component_status={
            component.id: component.initial_status for component in snapshot.components
        },
        connection_closed={
            connection.id: connection.initial_closed for connection in snapshot.connections
        },
        generator_running=set(),
        demand_w={
            component.id: component.demand_w or 0
            for component in snapshot.components
            if component.kind is ComponentKind.LOAD
        },
        battery_energy_mj={
            component.id: component.usable_energy_mj or 0
            for component in snapshot.components
            if component.kind is ComponentKind.UPS
        },
    )


def solve_capacity(snapshot: Snapshot, state: RuntimeState) -> CapacityFlowSummary:
    """Allocate loads by explicit priority using stable integral max-flow calls."""

    non_battery_sources = _non_battery_sources(snapshot, state)
    upstream_energized = _reachable_components(snapshot, state, non_battery_sources)
    battery_sources = tuple(
        sorted(
            component.id
            for component in snapshot.components
            if component.kind is ComponentKind.UPS
            and state.component_status[component.id] is Availability.AVAILABLE
            and state.battery_energy_mj[component.id] > 0
            and component.id not in upstream_energized
        )
    )
    sources = tuple(sorted((*non_battery_sources, *battery_sources)))
    allocation = _allocate(snapshot, state, sources)
    demand_w = sum(state.demand_w.values())
    served_w = sum(allocation.load_service_w.values())
    unserved_w = demand_w - served_w
    available_source_capacity_w = sum(
        snapshot.component_by_id[source_id].capacity_w for source_id in sources
    )
    used_source_capacity_w = sum(allocation.source_power_w.values())
    stranded_capacity_w = (
        min(unserved_w, max(0, available_source_capacity_w - used_source_capacity_w))
        if unserved_w
        else 0
    )
    redundancy_state = _redundancy_state(
        snapshot,
        state,
        non_battery_sources=non_battery_sources,
        battery_sources=battery_sources,
        demand_w=demand_w,
        served_w=served_w,
    )
    summary = CapacityFlowSummary(
        demand_w=demand_w,
        served_w=served_w,
        unserved_w=unserved_w,
        stranded_capacity_w=stranded_capacity_w,
        redundancy_state=redundancy_state,
        load_service_w=dict(sorted(allocation.load_service_w.items())),
        connection_flow_w=dict(sorted(allocation.connection_flow_w.items())),
        component_flow_w=dict(sorted(allocation.component_flow_w.items())),
        source_power_w=dict(sorted(allocation.source_power_w.items())),
        battery_source_ids=battery_sources,
    )
    _assert_capacity_invariants(snapshot, state, summary)
    return summary


@dataclass(slots=True)
class _Allocation:
    load_service_w: dict[str, int]
    connection_flow_w: dict[str, int]
    component_flow_w: dict[str, int]
    source_power_w: dict[str, int]


def _allocate(snapshot: Snapshot, state: RuntimeState, sources: tuple[str, ...]) -> _Allocation:
    used_component: dict[str, int] = defaultdict(int)
    used_connection: dict[str, int] = defaultdict(int)
    used_source: dict[str, int] = defaultdict(int)
    load_service: dict[str, int] = {}
    loads = sorted(
        (component for component in snapshot.components if component.kind is ComponentKind.LOAD),
        key=lambda item: (item.priority or 0, item.service_order or 0, item.id),
    )
    for load in loads:
        demand = state.demand_w[load.id]
        if (
            demand <= 0
            or not sources
            or state.component_status[load.id] is not Availability.AVAILABLE
        ):
            load_service[load.id] = 0
            continue
        capacities, tags = _build_network(
            snapshot,
            state,
            sources,
            load.id,
            demand,
            used_component,
            used_connection,
            used_source,
        )
        flow_value, edge_flow = _edmonds_karp(capacities, "@source", "@sink")
        load_service[load.id] = flow_value
        for edge, (category, identifier) in tags.items():
            value = edge_flow.get(edge, 0)
            if category == "component":
                used_component[identifier] += value
            elif category == "connection":
                used_connection[identifier] += value
            elif category == "source":
                used_source[identifier] += value
    return _Allocation(
        load_service_w=load_service,
        connection_flow_w=dict(used_connection),
        component_flow_w=dict(used_component),
        source_power_w=dict(used_source),
    )


def _build_network(
    snapshot: Snapshot,
    state: RuntimeState,
    sources: tuple[str, ...],
    load_id: str,
    demand_w: int,
    used_component: dict[str, int],
    used_connection: dict[str, int],
    used_source: dict[str, int],
) -> tuple[dict[Edge, int], dict[Edge, tuple[str, str]]]:
    capacities: dict[Edge, int] = {}
    tags: dict[Edge, tuple[str, str]] = {}
    for component in sorted(snapshot.components, key=lambda item: item.id):
        if state.component_status[component.id] is not Availability.AVAILABLE:
            continue
        remaining = component.capacity_w - used_component[component.id]
        if remaining <= 0:
            continue
        edge = (f"in:{component.id}", f"out:{component.id}")
        capacities[edge] = remaining
        tags[edge] = ("component", component.id)
    for connection in sorted(snapshot.connections, key=lambda item: item.id):
        if not state.connection_closed[connection.id]:
            continue
        if state.component_status[connection.from_component] is not Availability.AVAILABLE:
            continue
        if state.component_status[connection.to_component] is not Availability.AVAILABLE:
            continue
        remaining = connection.capacity_w - used_connection[connection.id]
        if remaining <= 0:
            continue
        connection_node = f"connection:{connection.id}"
        first = (f"out:{connection.from_component}", connection_node)
        second = (connection_node, f"in:{connection.to_component}")
        capacities[first] = remaining
        capacities[second] = remaining
        tags[first] = ("connection", connection.id)
    for source_id in sources:
        component = snapshot.component_by_id[source_id]
        remaining = component.capacity_w - used_source[source_id]
        if remaining <= 0 or state.component_status[source_id] is not Availability.AVAILABLE:
            continue
        edge = ("@source", f"in:{source_id}")
        capacities[edge] = remaining
        tags[edge] = ("source", source_id)
    capacities[(f"out:{load_id}", "@sink")] = demand_w
    return capacities, tags


def _edmonds_karp(
    capacities: dict[Edge, int], source: Node, sink: Node
) -> tuple[int, dict[Edge, int]]:
    """Return deterministic integral max flow and original-edge flows."""

    residual: dict[Node, dict[Node, int]] = defaultdict(dict)
    adjacency: dict[Node, set[Node]] = defaultdict(set)
    for (left, right), capacity in sorted(capacities.items()):
        if capacity < 0:
            raise InvariantError("engine.negative_capacity", "A residual capacity became negative.")
        residual[left][right] = residual[left].get(right, 0) + capacity
        residual[right].setdefault(left, 0)
        adjacency[left].add(right)
        adjacency[right].add(left)
    total = 0
    while True:
        parent = _breadth_first_parents(residual, adjacency, source, sink)
        if sink not in parent:
            break
        increment: int | None = None
        cursor = sink
        while cursor != source:
            previous = parent[cursor]
            if previous is None:
                raise InvariantError("engine.flow_path", "Broken augmenting path.")
            edge_capacity = residual[previous][cursor]
            increment = edge_capacity if increment is None else min(increment, edge_capacity)
            cursor = previous
        if increment is None or increment <= 0:
            raise InvariantError("engine.flow_increment", "Non-positive augmenting flow.")
        cursor = sink
        while cursor != source:
            previous = parent[cursor]
            if previous is None:
                raise InvariantError("engine.flow_path", "Broken augmenting path.")
            residual[previous][cursor] -= increment
            residual[cursor][previous] = residual[cursor].get(previous, 0) + increment
            cursor = previous
        total += increment
    edge_flow = {
        edge: capacity - residual[edge[0]].get(edge[1], 0) for edge, capacity in capacities.items()
    }
    return total, edge_flow


def _breadth_first_parents(
    residual: dict[Node, dict[Node, int]],
    adjacency: dict[Node, set[Node]],
    source: Node,
    sink: Node,
) -> dict[Node, Node | None]:
    """Find one shortest augmenting path in deterministic neighbor order."""

    parent: dict[Node, Node | None] = {source: None}
    queue: deque[Node] = deque([source])
    while queue and sink not in parent:
        left = queue.popleft()
        for right in sorted(adjacency[left]):
            if right not in parent and residual[left].get(right, 0) > 0:
                parent[right] = left
                queue.append(right)
                if right == sink:
                    break
    return parent


def _non_battery_sources(snapshot: Snapshot, state: RuntimeState) -> tuple[str, ...]:
    return tuple(
        sorted(
            component.id
            for component in snapshot.components
            if state.component_status[component.id] is Availability.AVAILABLE
            and (
                component.kind is ComponentKind.UTILITY
                or (
                    component.kind is ComponentKind.GENERATOR
                    and component.id in state.generator_running
                )
            )
        )
    )


def _reachable_components(
    snapshot: Snapshot, state: RuntimeState, source_ids: tuple[str, ...]
) -> set[str]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for connection in snapshot.connections:
        if (
            state.connection_closed[connection.id]
            and state.component_status[connection.from_component] is Availability.AVAILABLE
            and state.component_status[connection.to_component] is Availability.AVAILABLE
        ):
            adjacency[connection.from_component].append(connection.to_component)
    visited = set(source_ids)
    queue = deque(sorted(source_ids))
    while queue:
        current = queue.popleft()
        for target in sorted(adjacency[current]):
            if target not in visited:
                visited.add(target)
                queue.append(target)
    return visited


def _redundancy_state(
    snapshot: Snapshot,
    state: RuntimeState,
    *,
    non_battery_sources: tuple[str, ...],
    battery_sources: tuple[str, ...],
    demand_w: int,
    served_w: int,
) -> str:
    if demand_w == 0:
        return "no_demand"
    if served_w == 0:
        return "no_path"
    if served_w < demand_w:
        return "partial_service"
    qualifying_paths = {
        snapshot.component_by_id[source_id].path
        for source_id in non_battery_sources
        if _source_path_can_serve_total(snapshot, state, source_id, demand_w)
        and snapshot.component_by_id[source_id].path in {"A", "B"}
    }
    active_paths = {
        snapshot.component_by_id[source_id].path
        for source_id in non_battery_sources
        if snapshot.component_by_id[source_id].path in qualifying_paths
    }
    if len(active_paths) >= _TWO_N_PATH_COUNT:
        return "two_n"
    if len(active_paths) == 1:
        return "single_path"
    return "battery_backed" if battery_sources else "supported"


def _source_path_can_serve_total(
    snapshot: Snapshot, state: RuntimeState, source_id: str, demand_w: int
) -> bool:
    """Test a path after permitted load-input switching, preserving upstream isolations."""

    if demand_w == 0:
        return True
    source_path = snapshot.component_by_id[source_id].path
    candidate = state.clone()
    components = snapshot.component_by_id
    for connection in snapshot.connections:
        if (
            components[connection.to_component].kind is ComponentKind.LOAD
            and components[connection.from_component].path == source_path
            and state.component_status[connection.from_component] is Availability.AVAILABLE
            and state.component_status[connection.to_component] is Availability.AVAILABLE
        ):
            candidate.connection_closed[connection.id] = True
    allocation = _allocate(snapshot, candidate, (source_id,))
    return sum(allocation.load_service_w.values()) == demand_w


def _assert_capacity_invariants(
    snapshot: Snapshot, state: RuntimeState, summary: CapacityFlowSummary
) -> None:
    if summary.demand_w != summary.served_w + summary.unserved_w:
        raise InvariantError(
            "engine.power_balance", "Demand does not equal served plus unserved power."
        )
    for load_id, served_w in summary.load_service_w.items():
        if not 0 <= served_w <= state.demand_w[load_id]:
            raise InvariantError("engine.load_service", f"Invalid served power for {load_id}.")
    for connection_id, flow_w in summary.connection_flow_w.items():
        if not 0 <= flow_w <= snapshot.connection_by_id[connection_id].capacity_w:
            raise InvariantError("engine.connection_rating", f"Rating exceeded on {connection_id}.")
        if not state.connection_closed[connection_id] and flow_w:
            raise InvariantError(
                "engine.open_connection_flow", f"Open connection {connection_id} carries flow."
            )
    for component_id, flow_w in summary.component_flow_w.items():
        if not 0 <= flow_w <= snapshot.component_by_id[component_id].capacity_w:
            raise InvariantError("engine.component_rating", f"Rating exceeded on {component_id}.")
        if state.component_status[component_id] is not Availability.AVAILABLE and flow_w:
            raise InvariantError(
                "engine.unavailable_component_flow", f"Unavailable {component_id} carries flow."
            )
    for ups_id in summary.battery_source_ids:
        if (
            not 0
            < state.battery_energy_mj[ups_id]
            <= (snapshot.component_by_id[ups_id].usable_energy_mj or 0)
        ):
            raise InvariantError(
                "engine.battery_bounds", f"Battery energy outside bounds for {ups_id}."
            )
