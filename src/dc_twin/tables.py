"""SQLAlchemy Core tables for immutable PostgreSQL persistence."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
json_document = JSON().with_variant(JSONB(), "postgresql")

design_snapshots = Table(
    "design_snapshots",
    metadata,
    Column("content_hash", String(64), primary_key=True),
    Column("snapshot_id", String(64), nullable=False, index=True),
    Column("schema_version", String(16), nullable=False),
    Column("content", json_document, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("length(content_hash) = 64", name="ck_design_snapshots_hash_length"),
)

scenarios = Table(
    "scenarios",
    metadata,
    Column("content_hash", String(64), primary_key=True),
    Column("scenario_id", String(64), nullable=False, index=True),
    Column(
        "snapshot_hash",
        String(64),
        ForeignKey("design_snapshots.content_hash", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("schema_version", String(16), nullable=False),
    Column("content", json_document, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("length(content_hash) = 64", name="ck_scenarios_hash_length"),
)

simulation_runs = Table(
    "simulation_runs",
    metadata,
    Column("run_id", String(32), primary_key=True),
    Column("computation_hash", String(64), nullable=False, unique=True),
    Column(
        "snapshot_hash",
        String(64),
        ForeignKey("design_snapshots.content_hash", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "scenario_hash",
        String(64),
        ForeignKey("scenarios.content_hash", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("engine_version", String(16), nullable=False),
    Column("result", json_document, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("length(computation_hash) = 64", name="ck_simulation_runs_hash_length"),
)
