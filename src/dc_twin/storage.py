"""Immutable run storage ports and adapters."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol

from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.exc import IntegrityError

from dc_twin.tables import design_snapshots, scenarios, simulation_runs


class RunStore(Protocol):
    def save_run(
        self,
        result: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any],
        scenario: Mapping[str, Any],
    ) -> None: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def ready(self) -> bool: ...


class MemoryRunStore:
    """Thread-safe bounded adapter for local demo and tests."""

    def __init__(self, *, max_runs: int = 100) -> None:
        self._max_runs = max_runs
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save_run(
        self,
        result: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any],
        scenario: Mapping[str, Any],
    ) -> None:
        del snapshot, scenario
        run_id = str(result["run_id"])
        with self._lock:
            if run_id not in self._runs and len(self._runs) >= self._max_runs:
                oldest = next(iter(self._runs))
                self._runs.pop(oldest)
            self._runs[run_id] = deepcopy(dict(result))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            result = self._runs.get(run_id)
            return deepcopy(result) if result is not None else None

    def ready(self) -> bool:
        return True


class PostgresRunStore:
    """SQLAlchemy adapter; migrations must be applied before application startup."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)

    def save_run(
        self,
        result: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any],
        scenario: Mapping[str, Any],
    ) -> None:
        snapshot_hash = str(result["snapshot_hash"])
        scenario_hash = str(result["scenario_hash"])
        run_id = str(result["run_id"])
        try:
            with self._engine.begin() as connection:
                if (
                    connection.scalar(
                        select(design_snapshots.c.content_hash).where(
                            design_snapshots.c.content_hash == snapshot_hash
                        )
                    )
                    is None
                ):
                    connection.execute(
                        insert(design_snapshots).values(
                            content_hash=snapshot_hash,
                            snapshot_id=str(snapshot["snapshot_id"]),
                            schema_version=str(snapshot["schema_version"]),
                            content=dict(snapshot),
                        )
                    )
                if (
                    connection.scalar(
                        select(scenarios.c.content_hash).where(
                            scenarios.c.content_hash == scenario_hash
                        )
                    )
                    is None
                ):
                    connection.execute(
                        insert(scenarios).values(
                            content_hash=scenario_hash,
                            scenario_id=str(scenario["scenario_id"]),
                            snapshot_hash=snapshot_hash,
                            schema_version=str(scenario["schema_version"]),
                            content=dict(scenario),
                        )
                    )
                if (
                    connection.scalar(
                        select(simulation_runs.c.run_id).where(simulation_runs.c.run_id == run_id)
                    )
                    is None
                ):
                    connection.execute(
                        insert(simulation_runs).values(
                            run_id=run_id,
                            computation_hash=str(result["computation_hash"]),
                            snapshot_hash=snapshot_hash,
                            scenario_hash=scenario_hash,
                            engine_version=str(result["engine_version"]),
                            result=dict(result),
                        )
                    )
        except IntegrityError:
            existing = self.get_run(run_id)
            if existing is None or existing.get("computation_hash") != result.get(
                "computation_hash"
            ):
                raise

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            result = connection.scalar(
                select(simulation_runs.c.result).where(simulation_runs.c.run_id == run_id)
            )
        return dict(result) if result is not None else None

    def ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
