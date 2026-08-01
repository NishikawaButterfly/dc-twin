"""Framework-independent immutable domain contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ComponentKind(StrEnum):
    UTILITY = "utility"
    GENERATOR = "generator"
    SWITCHGEAR = "switchgear"
    TRANSFORMER = "transformer"
    UPS = "ups"
    ATS = "ats"
    STS = "sts"
    PDU = "pdu"
    LOAD = "load"


class Availability(StrEnum):
    AVAILABLE = "available"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


class EventKind(StrEnum):
    COMPONENT_FAILURE = "component_failure"
    COMPONENT_RESTORE = "component_restore"
    MAINTENANCE_START = "maintenance_start"
    MAINTENANCE_END = "maintenance_end"
    GENERATOR_RUNNING = "generator_running"
    GENERATOR_START_FAILURE = "generator_start_failure"
    ATOMIC_TRANSFER = "atomic_transfer"
    LOAD_STEP = "load_step"


@dataclass(frozen=True, slots=True)
class Component:
    id: str
    label: str
    kind: ComponentKind
    path: str
    capacity_w: int
    initial_status: Availability
    demand_w: int | None = None
    priority: int | None = None
    service_order: int | None = None
    usable_energy_mj: int | None = None
    low_energy_threshold_pct: int | None = None
    start_delay_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Connection:
    id: str
    from_component: str
    to_component: str
    capacity_w: int
    initial_closed: bool


@dataclass(frozen=True, slots=True)
class RedundancyGroup:
    id: str
    mode: str
    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Snapshot:
    schema_id: str
    schema_version: str
    snapshot_id: str
    design_revision: str
    data_classification: str
    provenance: dict[str, str]
    units: dict[str, str]
    assumptions: tuple[str, ...]
    components: tuple[Component, ...]
    connections: tuple[Connection, ...]
    redundancy_groups: tuple[RedundancyGroup, ...]
    source_hash: str

    @property
    def component_by_id(self) -> dict[str, Component]:
        return {component.id: component for component in self.components}

    @property
    def connection_by_id(self) -> dict[str, Connection]:
        return {connection.id: connection for connection in self.connections}


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    time_ms: int
    kind: EventKind
    component_id: str | None = None
    status: Availability | None = None
    open_connection_ids: tuple[str, ...] = ()
    close_connection_ids: tuple[str, ...] = ()
    demand_w: int | None = None

    @property
    def semantic_priority(self) -> int:
        priorities = {
            EventKind.COMPONENT_FAILURE: 10,
            EventKind.GENERATOR_START_FAILURE: 10,
            EventKind.MAINTENANCE_START: 20,
            EventKind.COMPONENT_RESTORE: 30,
            EventKind.MAINTENANCE_END: 30,
            EventKind.GENERATOR_RUNNING: 35,
            EventKind.ATOMIC_TRANSFER: 40,
            EventKind.LOAD_STEP: 50,
        }
        return priorities[self.kind]


@dataclass(frozen=True, slots=True)
class Scenario:
    schema_id: str
    schema_version: str
    scenario_id: str
    label: str
    snapshot_id: str
    horizon_ms: int
    resolution_ms: int
    data_classification: str
    events: tuple[Event, ...]
    source_hash: str


@dataclass(slots=True)
class RuntimeState:
    """Mutable state is confined to one simulation invocation."""

    component_status: dict[str, Availability]
    connection_closed: dict[str, bool]
    generator_running: set[str]
    demand_w: dict[str, int]
    battery_energy_mj: dict[str, int]
    low_energy_alarm_raised: set[str] = field(default_factory=set)
    depletion_alarm_raised: set[str] = field(default_factory=set)

    def canonical(self) -> dict[str, Any]:
        return {
            "battery_energy_mj": dict(sorted(self.battery_energy_mj.items())),
            "component_status": {
                key: value.value for key, value in sorted(self.component_status.items())
            },
            "connection_closed": dict(sorted(self.connection_closed.items())),
            "demand_w": dict(sorted(self.demand_w.items())),
            "depletion_alarm_raised": sorted(self.depletion_alarm_raised),
            "generator_running": sorted(self.generator_running),
            "low_energy_alarm_raised": sorted(self.low_energy_alarm_raised),
        }

    def clone(self) -> RuntimeState:
        return RuntimeState(
            component_status=dict(self.component_status),
            connection_closed=dict(self.connection_closed),
            generator_running=set(self.generator_running),
            demand_w=dict(self.demand_w),
            battery_energy_mj=dict(self.battery_energy_mj),
            low_energy_alarm_raised=set(self.low_energy_alarm_raised),
            depletion_alarm_raised=set(self.depletion_alarm_raised),
        )
