"""Deterministic event engine with exact integer energy accounting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dc_twin.canonical import sha256_json
from dc_twin.capacity import CapacityFlowSummary, initial_state, solve_capacity
from dc_twin.errors import ContractError, InvariantError, TopologyError
from dc_twin.models import (
    Availability,
    ComponentKind,
    Event,
    EventKind,
    RuntimeState,
    Scenario,
    Snapshot,
)
from dc_twin.telemetry import build_telemetry
from dc_twin.validation import MAX_TRANSITIONS

ENGINE_VERSION = "1.0.0"


@dataclass(slots=True)
class _Accumulator:
    demanded_energy_mj: int = 0
    served_energy_mj: int = 0
    unserved_energy_mj: int = 0
    interruption_duration_ms: int = 0
    interruption_count: int = 0
    peak_demand_w: int = 0
    peak_served_w: int = 0
    minimum_served_w: int | None = None
    peak_stranded_capacity_w: int = 0
    previous_unserved: bool = False
    redundancy_states: list[str] = field(default_factory=list)

    def add_segment(self, summary: CapacityFlowSummary, duration_ms: int) -> None:
        self.demanded_energy_mj += summary.demand_w * duration_ms
        self.served_energy_mj += summary.served_w * duration_ms
        self.unserved_energy_mj += summary.unserved_w * duration_ms
        is_unserved = summary.unserved_w > 0
        if is_unserved:
            self.interruption_duration_ms += duration_ms
            if not self.previous_unserved:
                self.interruption_count += 1
        self.previous_unserved = is_unserved
        self.peak_demand_w = max(self.peak_demand_w, summary.demand_w)
        self.peak_served_w = max(self.peak_served_w, summary.served_w)
        if summary.demand_w > 0:
            self.minimum_served_w = (
                summary.served_w
                if self.minimum_served_w is None
                else min(self.minimum_served_w, summary.served_w)
            )
        self.peak_stranded_capacity_w = max(
            self.peak_stranded_capacity_w, summary.stranded_capacity_w
        )
        self.redundancy_states.append(summary.redundancy_state)


class _AlarmLedger:
    def __init__(self) -> None:
        self.alarms: list[dict[str, Any]] = []
        self.active: dict[str, str] = {}

    def raise_alarm(
        self,
        *,
        time_ms: int,
        severity: str,
        code: str,
        message: str,
        component_id: str | None,
        causal_event_id: str,
        active_key: str | None = None,
    ) -> str:
        key = active_key or f"{code}:{component_id or 'system'}"
        existing = self.active.get(key)
        if existing is not None:
            return existing
        alarm_id = f"alarm-{len(self.alarms) + 1:04d}-{code.lower().replace('_', '-')}"
        self.alarms.append(
            {
                "id": alarm_id,
                "time_ms": time_ms,
                "severity": severity,
                "code": code,
                "message": message,
                "component_id": component_id,
                "causal_event_id": causal_event_id,
            }
        )
        self.active[key] = alarm_id
        return alarm_id

    def clear(self, key: str) -> list[str]:
        alarm_id = self.active.pop(key, None)
        return [alarm_id] if alarm_id is not None else []


class _Run:
    """Mutable transition bookkeeping shared by external and internal processing."""

    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.alarms = _AlarmLedger()
        self.state = initial_state(snapshot)
        self.summary = solve_capacity(snapshot, self.state)
        self.transitions: list[dict[str, Any]] = []
        self.sequence = 0
        self.current_time = 0
        self.causes = ["system.initialized"]
        self._record(
            time_ms=0,
            event_id="system.initialized",
            event_kind="system_initialization",
            target_id=None,
            before_state_hash=_state_hash(self.state),
            raised=[],
            cleared=[],
        )

    def _record(
        self,
        *,
        time_ms: int,
        event_id: str,
        event_kind: str,
        target_id: str | None,
        before_state_hash: str,
        raised: list[str],
        cleared: list[str],
    ) -> None:
        self.transitions.append(
            {
                "sequence": self.sequence,
                "time_ms": time_ms,
                "event_id": event_id,
                "event_kind": event_kind,
                "target_id": target_id,
                "before_state_hash": before_state_hash,
                "after_state_hash": _state_hash(self.state),
                "alarms_raised": raised,
                "alarms_cleared": cleared,
            }
        )
        self.sequence += 1
        _check_transition_limit(self.sequence)

    def process_external(
        self, event: Event, *, service_baseline: CapacityFlowSummary | None = None
    ) -> None:
        before_hash = _state_hash(self.state)
        candidate = self.state.clone()
        direct_raised, direct_cleared = _apply_event(self.snapshot, candidate, event, self.alarms)
        _validate_runtime_switching(self.snapshot, candidate)
        self.state = candidate
        self.summary = solve_capacity(self.snapshot, self.state)
        service_raised: list[str] = []
        service_cleared: list[str] = []
        if service_baseline is not None:
            service_raised, service_cleared = _service_alarms(
                self.alarms,
                time_ms=event.time_ms,
                event_id=event.id,
                before=service_baseline,
                after=self.summary,
            )
        self._record(
            time_ms=event.time_ms,
            event_id=event.id,
            event_kind=event.kind.value,
            target_id=event.component_id,
            before_state_hash=before_hash,
            raised=[*direct_raised, *service_raised],
            cleared=[*direct_cleared, *service_cleared],
        )
        self.causes = [event.id]

    def process_internal(self, kind: str, component_id: str) -> None:
        before_hash = _state_hash(self.state)
        before_summary = self.summary
        event_id = f"system.{kind}.{component_id}.{self.current_time}"
        raised = [self._raise_internal_alarm(kind, component_id, event_id)]
        self.summary = solve_capacity(self.snapshot, self.state)
        service_raised, service_cleared = _service_alarms(
            self.alarms,
            time_ms=self.current_time,
            event_id=event_id,
            before=before_summary,
            after=self.summary,
        )
        self._record(
            time_ms=self.current_time,
            event_id=event_id,
            event_kind=kind,
            target_id=component_id,
            before_state_hash=before_hash,
            raised=[*raised, *service_raised],
            cleared=service_cleared,
        )
        self.causes = [event_id]

    def _raise_internal_alarm(self, kind: str, component_id: str, event_id: str) -> str:
        if kind == "ups_low_energy":
            self.state.low_energy_alarm_raised.add(component_id)
            return self.alarms.raise_alarm(
                time_ms=self.current_time,
                severity="warning",
                code="ups_low_energy",
                message=f"{component_id} reached its modeled low-energy threshold.",
                component_id=component_id,
                causal_event_id=event_id,
            )
        if kind == "ups_depleted":
            if self.state.battery_energy_mj[component_id] != 0:
                raise InvariantError(
                    "engine.depletion_timing",
                    f"{component_id} depletion did not occur at zero energy.",
                )
            self.state.depletion_alarm_raised.add(component_id)
            return self.alarms.raise_alarm(
                time_ms=self.current_time,
                severity="critical",
                code="ups_energy_depleted",
                message=f"{component_id} exhausted its modeled usable battery energy.",
                component_id=component_id,
                causal_event_id=event_id,
            )
        raise InvariantError("engine.internal_event", f"Unknown internal transition {kind}.")


def simulate(snapshot: Snapshot, scenario: Scenario) -> dict[str, Any]:
    """Run one bounded deterministic scenario and return an immutable result envelope."""

    if scenario.snapshot_id != snapshot.snapshot_id:
        raise ContractError(
            "scenario.snapshot_mismatch", "Scenario and snapshot identifiers differ."
        )
    run = _Run(snapshot)
    timeline: list[dict[str, Any]] = []
    accumulator = _Accumulator()
    event_index = 0
    if event_index < len(scenario.events) and scenario.events[event_index].time_ms == 0:
        event_index = _process_external_group(
            scenario.events,
            event_index,
            summary_getter=lambda: run.summary,
            processor=run.process_external,
        )

    while run.current_time < scenario.horizon_ms:
        next_external_time = (
            scenario.events[event_index].time_ms
            if event_index < len(scenario.events)
            else scenario.horizon_ms
        )
        milestone = _next_battery_milestone(snapshot, run.state, run.summary, run.current_time)
        next_internal_time = milestone[0] if milestone is not None else scenario.horizon_ms
        next_resolution_time = min(
            ((run.current_time // scenario.resolution_ms) + 1) * scenario.resolution_ms,
            scenario.horizon_ms,
        )
        boundary = min(
            next_external_time,
            next_internal_time,
            next_resolution_time,
            scenario.horizon_ms,
        )
        if boundary < run.current_time:
            raise InvariantError("engine.time_regression", "Simulation time moved backwards.")
        if boundary > run.current_time:
            duration_ms = boundary - run.current_time
            _integrate_batteries(run.state, run.summary, duration_ms)
            accumulator.add_segment(run.summary, duration_ms)
            timeline.append(
                _segment(
                    start_ms=run.current_time,
                    end_ms=boundary,
                    summary=run.summary,
                    state=run.state,
                    causal_event_ids=run.causes,
                )
            )
            run.current_time = boundary
        if milestone is not None and milestone[0] == run.current_time:
            run.process_internal(milestone[1], milestone[2])
            continue
        if (
            event_index < len(scenario.events)
            and scenario.events[event_index].time_ms == run.current_time
        ):
            event_index = _process_external_group(
                scenario.events,
                event_index,
                summary_getter=lambda: run.summary,
                processor=run.process_external,
            )
        if run.current_time == scenario.horizon_ms:
            break

    if event_index != len(scenario.events):
        raise InvariantError("engine.unconsumed_events", "Not every validated event was consumed.")
    _assert_energy_balance(accumulator)
    metrics = _build_metrics(accumulator)
    explanations = _build_explanations(snapshot, scenario, metrics)
    semantic_result: dict[str, Any] = {
        "schema_id": "dc-twin.simulation-result",
        "schema_version": "1.0.0",
        "engine_version": ENGINE_VERSION,
        "snapshot_hash": snapshot.source_hash,
        "scenario_hash": scenario.source_hash,
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "label": scenario.label,
            "horizon_ms": scenario.horizon_ms,
        },
        "metrics": metrics,
        "timeline": timeline,
        "transitions": run.transitions,
        "alarms": run.alarms.alarms,
        "explanations": explanations,
    }
    telemetry = build_telemetry(snapshot, timeline)
    semantic_result["telemetry"] = telemetry
    computation_hash = sha256_json(semantic_result)
    return {
        "run_id": f"run-{computation_hash[:16]}",
        "computation_hash": computation_hash,
        **semantic_result,
    }


def verify_replay(snapshot: Snapshot, scenario: Scenario, expected_hash: str) -> dict[str, Any]:
    """Replay and report semantic-hash equality without mutating the original result."""

    replay = simulate(snapshot, scenario)
    return {
        "expected_computation_hash": expected_hash,
        "actual_computation_hash": replay["computation_hash"],
        "matches": replay["computation_hash"] == expected_hash,
        "replay_run_id": replay["run_id"],
    }


_STATUS_EVENT_KINDS = frozenset(
    {
        EventKind.COMPONENT_FAILURE,
        EventKind.COMPONENT_RESTORE,
        EventKind.MAINTENANCE_START,
        EventKind.MAINTENANCE_END,
    }
)


def _apply_event(
    snapshot: Snapshot,
    state: RuntimeState,
    event: Event,
    alarms: _AlarmLedger,
) -> tuple[list[str], list[str]]:
    raised: list[str] = []
    cleared: list[str] = []
    component_id = event.component_id
    if event.kind is EventKind.ATOMIC_TRANSFER:
        for connection_id in event.open_connection_ids:
            state.connection_closed[connection_id] = False
        for connection_id in event.close_connection_ids:
            state.connection_closed[connection_id] = True
        return raised, cleared
    if component_id is None:
        raise InvariantError("engine.event_target", f"{event.id} has no target.")
    if event.kind in _STATUS_EVENT_KINDS:
        return _apply_status_event(snapshot, state, event, alarms, component_id)
    if event.kind is EventKind.GENERATOR_RUNNING:
        state.component_status[component_id] = Availability.AVAILABLE
        state.generator_running.add(component_id)
        cleared.extend(alarms.clear(f"generator_start_failed:{component_id}"))
    elif event.kind is EventKind.GENERATOR_START_FAILURE:
        state.component_status[component_id] = Availability.FAILED
        state.generator_running.discard(component_id)
        raised.append(
            alarms.raise_alarm(
                time_ms=event.time_ms,
                severity="critical",
                code="generator_start_failed",
                message=f"{component_id} failed its modeled start sequence.",
                component_id=component_id,
                causal_event_id=event.id,
            )
        )
    elif event.kind is EventKind.LOAD_STEP:
        if event.demand_w is None:
            raise InvariantError("engine.load_step", f"{event.id} has no demand value.")
        state.demand_w[component_id] = event.demand_w
    else:
        raise InvariantError("engine.event_kind", f"Unsupported event kind {event.kind}.")
    return raised, cleared


def _apply_status_event(
    snapshot: Snapshot,
    state: RuntimeState,
    event: Event,
    alarms: _AlarmLedger,
    component_id: str,
) -> tuple[list[str], list[str]]:
    raised: list[str] = []
    cleared: list[str] = []
    if event.status is None:
        raise InvariantError("engine.event_status", f"{event.id} has no status.")
    state.component_status[component_id] = event.status
    if snapshot.component_by_id[component_id].kind is ComponentKind.GENERATOR and (
        event.status is not Availability.AVAILABLE
    ):
        state.generator_running.discard(component_id)
    if event.kind is EventKind.COMPONENT_FAILURE:
        raised.append(
            alarms.raise_alarm(
                time_ms=event.time_ms,
                severity="critical",
                code="component_failed",
                message=f"{component_id} entered the modeled failed state.",
                component_id=component_id,
                causal_event_id=event.id,
            )
        )
    elif event.kind is EventKind.COMPONENT_RESTORE:
        cleared.extend(alarms.clear(f"component_failed:{component_id}"))
    elif event.kind is EventKind.MAINTENANCE_START:
        raised.append(
            alarms.raise_alarm(
                time_ms=event.time_ms,
                severity="info",
                code="maintenance_active",
                message=f"{component_id} entered planned maintenance.",
                component_id=component_id,
                causal_event_id=event.id,
            )
        )
    elif event.kind is EventKind.MAINTENANCE_END:
        cleared.extend(alarms.clear(f"maintenance_active:{component_id}"))
    return raised, cleared


def _process_external_group(
    events: tuple[Event, ...],
    start_index: int,
    *,
    summary_getter: Callable[[], CapacityFlowSummary],
    processor: Callable[..., None],
) -> int:
    """Apply equal-time events deterministically and evaluate service after the full group."""

    time_ms = events[start_index].time_ms
    end_index = start_index
    while end_index < len(events) and events[end_index].time_ms == time_ms:
        end_index += 1
    baseline = summary_getter()
    for index in range(start_index, end_index):
        processor(events[index], service_baseline=baseline if index == end_index - 1 else None)
    return end_index


def _validate_runtime_switching(snapshot: Snapshot, state: RuntimeState) -> None:
    incoming: dict[str, list[str]] = {}
    for connection in snapshot.connections:
        incoming.setdefault(connection.to_component, []).append(connection.id)
    for component in snapshot.components:
        if component.kind not in {ComponentKind.ATS, ComponentKind.STS}:
            continue
        closed_inputs = [
            connection_id
            for connection_id in incoming.get(component.id, [])
            if state.connection_closed[connection_id]
        ]
        if len(closed_inputs) > 1:
            raise TopologyError(
                "topology.parallel_sources",
                f"Runtime transfer would parallel inputs at {component.id}: "
                f"{', '.join(closed_inputs)}.",
            )


def _service_alarms(
    alarms: _AlarmLedger,
    *,
    time_ms: int,
    event_id: str,
    before: CapacityFlowSummary,
    after: CapacityFlowSummary,
) -> tuple[list[str], list[str]]:
    raised: list[str] = []
    cleared: list[str] = []
    if before.unserved_w == 0 and after.unserved_w > 0:
        raised.append(
            alarms.raise_alarm(
                time_ms=time_ms,
                severity="critical",
                code="load_unserved",
                message=f"Modeled unserved load increased to {after.unserved_w} W.",
                component_id=None,
                causal_event_id=event_id,
                active_key="load_unserved:system",
            )
        )
    elif before.unserved_w > 0 and after.unserved_w == 0:
        cleared.extend(alarms.clear("load_unserved:system"))
    return raised, cleared


def _next_battery_milestone(
    snapshot: Snapshot,
    state: RuntimeState,
    summary: CapacityFlowSummary,
    current_time: int,
) -> tuple[int, str, str] | None:
    candidates: list[tuple[int, int, str, str]] = []
    for ups_id in summary.battery_source_ids:
        power_w = summary.source_power_w.get(ups_id, 0)
        if power_w <= 0:
            continue
        component = snapshot.component_by_id[ups_id]
        energy_mj = state.battery_energy_mj[ups_id]
        usable_mj = component.usable_energy_mj or 0
        threshold_mj = usable_mj * (component.low_energy_threshold_pct or 0) // 100
        if ups_id not in state.low_energy_alarm_raised and energy_mj >= threshold_mj:
            delta_energy = energy_mj - threshold_mj
            delta_ms = _exact_duration(delta_energy, power_w, ups_id, "low-energy threshold")
            candidates.append((current_time + delta_ms, 10, ups_id, "ups_low_energy"))
        else:
            delta_ms = _exact_duration(energy_mj, power_w, ups_id, "depletion")
            candidates.append((current_time + delta_ms, 20, ups_id, "ups_depleted"))
    if not candidates:
        return None
    time_ms, _priority, component_id, kind = min(candidates)
    return time_ms, kind, component_id


def _exact_duration(energy_mj: int, power_w: int, component_id: str, label: str) -> int:
    if energy_mj < 0 or power_w <= 0:
        raise InvariantError("engine.energy_state", f"Invalid energy state for {component_id}.")
    duration_ms, remainder = divmod(energy_mj, power_w)
    if remainder:
        raise ContractError(
            "scenario.temporal_precision",
            f"{component_id} reaches {label} between millisecond boundaries; "
            "v1 requires exact ms-grid milestones.",
        )
    return duration_ms


def _integrate_batteries(
    state: RuntimeState, summary: CapacityFlowSummary, duration_ms: int
) -> None:
    for ups_id in summary.battery_source_ids:
        discharge_mj = summary.source_power_w.get(ups_id, 0) * duration_ms
        if discharge_mj > state.battery_energy_mj[ups_id]:
            raise InvariantError("engine.energy_overdraw", f"Battery overdraw for {ups_id}.")
        state.battery_energy_mj[ups_id] -= discharge_mj


def _segment(
    *,
    start_ms: int,
    end_ms: int,
    summary: CapacityFlowSummary,
    state: RuntimeState,
    causal_event_ids: list[str],
) -> dict[str, Any]:
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "demand_w": summary.demand_w,
        "served_w": summary.served_w,
        "unserved_w": summary.unserved_w,
        "stranded_capacity_w": summary.stranded_capacity_w,
        "redundancy_state": summary.redundancy_state,
        "battery_energy_mj": dict(sorted(state.battery_energy_mj.items())),
        "source_power_w": summary.source_power_w,
        "load_service_w": summary.load_service_w,
        "connection_flow_w": summary.connection_flow_w,
        "state_hash": _state_hash(state),
        "causal_event_ids": list(causal_event_ids),
    }


def _state_hash(state: RuntimeState) -> str:
    return sha256_json(state.canonical())


def _build_metrics(accumulator: _Accumulator) -> dict[str, Any]:
    demanded = accumulator.demanded_energy_mj
    served = accumulator.served_energy_mj
    service_ratio_ppm = (
        1_000_000 if demanded == 0 else (served * 1_000_000 + demanded // 2) // demanded
    )
    severity = {
        "no_path": 0,
        "partial_service": 1,
        "battery_backed": 2,
        "single_path": 3,
        "supported": 4,
        "two_n": 5,
        "no_demand": 6,
    }
    observed = accumulator.redundancy_states or ["no_demand"]
    modeled_state = min(observed, key=lambda item: severity[item])
    return {
        "demanded_energy_mj": demanded,
        "served_energy_mj": served,
        "unserved_energy_mj": accumulator.unserved_energy_mj,
        "service_ratio_ppm": service_ratio_ppm,
        "interruption_duration_ms": accumulator.interruption_duration_ms,
        "interruption_count": accumulator.interruption_count,
        "peak_demand_w": accumulator.peak_demand_w,
        "peak_served_w": accumulator.peak_served_w,
        "minimum_served_w": accumulator.minimum_served_w or 0,
        "peak_stranded_capacity_w": accumulator.peak_stranded_capacity_w,
        "modeled_redundancy_state": modeled_state,
    }


def _build_explanations(
    snapshot: Snapshot, scenario: Scenario, metrics: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    event_refs = [event.id for event in scenario.events]
    common_inputs = [
        f"snapshot:{snapshot.snapshot_id}",
        f"scenario:{scenario.scenario_id}",
    ]
    return {
        "unserved_energy_mj": {
            "formula": "sum(unserved_w * segment_duration_ms)",
            "input_refs": common_inputs,
            "event_refs": event_refs,
            "summary": f"Integrated {metrics['unserved_energy_mj']} mJ of unmet modeled demand.",
        },
        "service_ratio_ppm": {
            "formula": "round_half_up(served_energy_mj * 1_000_000 / demanded_energy_mj)",
            "input_refs": common_inputs,
            "event_refs": event_refs,
            "summary": "Scenario service ratio only; this is not annual availability.",
        },
        "interruption_duration_ms": {
            "formula": "sum(segment_duration_ms where unserved_w > 0)",
            "input_refs": common_inputs,
            "event_refs": event_refs,
            "summary": "Duration of intervals with any modeled unserved load.",
        },
        "peak_stranded_capacity_w": {
            "formula": "max(min(unserved_w, available_source_capacity_w - used_source_capacity_w))",
            "input_refs": common_inputs,
            "event_refs": event_refs,
            "summary": "Capacity isolated from unmet load; this is not ordinary spare margin.",
        },
        "modeled_redundancy_state": {
            "formula": "worst observed deterministic segment state",
            "input_refs": common_inputs,
            "event_refs": event_refs,
            "summary": (
                "Scenario evidence only; it is not a Tier or code-compliance classification."
            ),
        },
    }


def _assert_energy_balance(accumulator: _Accumulator) -> None:
    if accumulator.demanded_energy_mj != (
        accumulator.served_energy_mj + accumulator.unserved_energy_mj
    ):
        raise InvariantError(
            "engine.energy_balance", "Demanded energy does not equal served plus unserved energy."
        )


def _check_transition_limit(count: int) -> None:
    if count > MAX_TRANSITIONS:
        raise ContractError(
            "scenario.transition_limit", f"Simulation exceeded {MAX_TRANSITIONS} transitions."
        )
