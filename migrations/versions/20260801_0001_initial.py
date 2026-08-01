"""Create immutable design, scenario, and simulation run tables.

Revision ID: 20260801_0001
Revises: None
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "design_snapshots",
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_design_snapshots_hash_length"),
        sa.PrimaryKeyConstraint("content_hash"),
    )
    op.create_index("ix_design_snapshots_snapshot_id", "design_snapshots", ["snapshot_id"])
    op.create_table(
        "scenarios",
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_scenarios_hash_length"),
        sa.ForeignKeyConstraint(
            ["snapshot_hash"], ["design_snapshots.content_hash"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("content_hash"),
    )
    op.create_index("ix_scenarios_scenario_id", "scenarios", ["scenario_id"])
    op.create_table(
        "simulation_runs",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("computation_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("scenario_hash", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=16), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("length(computation_hash) = 64", name="ck_simulation_runs_hash_length"),
        sa.ForeignKeyConstraint(
            ["scenario_hash"], ["scenarios.content_hash"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_hash"], ["design_snapshots.content_hash"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("computation_hash"),
    )


def downgrade() -> None:
    op.drop_table("simulation_runs")
    op.drop_index("ix_scenarios_scenario_id", table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_index("ix_design_snapshots_snapshot_id", table_name="design_snapshots")
    op.drop_table("design_snapshots")

