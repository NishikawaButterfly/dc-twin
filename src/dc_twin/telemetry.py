"""Synthetic telemetry derived from recorded simulation segments."""

from __future__ import annotations

from typing import Any

from dc_twin.errors import ResourceLimitError
from dc_twin.models import Snapshot
from dc_twin.validation import MAX_TELEMETRY_POINTS


def build_telemetry(snapshot: Snapshot, timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build synthetic review telemetry from the same authoritative timeline state."""

    points: list[dict[str, Any]] = []

    def append(
        *,
        time_ms: int,
        component_id: str,
        metric: str,
        value: int | str,
        unit: str,
        state_hash: str,
    ) -> None:
        if len(points) >= MAX_TELEMETRY_POINTS:
            raise ResourceLimitError(
                "result.telemetry_limit",
                f"Result exceeds {MAX_TELEMETRY_POINTS} synthetic telemetry points.",
            )
        points.append(
            {
                "sequence": len(points),
                "time_ms": time_ms,
                "component_id": component_id,
                "metric": metric,
                "value": value,
                "unit": unit,
                "quality": "synthetic",
                "state_hash": state_hash,
            }
        )

    component_ids = snapshot.component_by_id.keys()
    for segment in timeline:
        time_ms = int(segment["end_ms"])
        state_hash = str(segment["state_hash"])
        append(
            time_ms=time_ms,
            component_id="system",
            metric="demand_w",
            value=int(segment["demand_w"]),
            unit="W",
            state_hash=state_hash,
        )
        append(
            time_ms=time_ms,
            component_id="system",
            metric="served_w",
            value=int(segment["served_w"]),
            unit="W",
            state_hash=state_hash,
        )
        append(
            time_ms=time_ms,
            component_id="system",
            metric="unserved_w",
            value=int(segment["unserved_w"]),
            unit="W",
            state_hash=state_hash,
        )
        for component_id, energy_mj in sorted(segment["battery_energy_mj"].items()):
            if component_id not in component_ids:
                continue
            append(
                time_ms=time_ms,
                component_id=component_id,
                metric="stored_energy_mj",
                value=int(energy_mj),
                unit="mJ",
                state_hash=state_hash,
            )
        for component_id, power_w in sorted(segment["source_power_w"].items()):
            append(
                time_ms=time_ms,
                component_id=component_id,
                metric="source_power_w",
                value=int(power_w),
                unit="W",
                state_hash=state_hash,
            )
        for component_id, power_w in sorted(segment["load_service_w"].items()):
            append(
                time_ms=time_ms,
                component_id=component_id,
                metric="served_power_w",
                value=int(power_w),
                unit="W",
                state_hash=state_hash,
            )
        append(
            time_ms=time_ms,
            component_id="system",
            metric="modeled_redundancy_state",
            value=str(segment["redundancy_state"]),
            unit="state",
            state_hash=state_hash,
        )
    return points
