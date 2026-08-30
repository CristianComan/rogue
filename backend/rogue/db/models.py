"""SQLAlchemy ORM models for scenario persistence (M2).

Scenario/ScenarioDraft/ScenarioVersion content beyond the columns needed
for querying is stored as a JSONB ``document`` — the M1 domain model's own
``model_dump(mode="json")`` output — rather than a fully normalized schema
per nested entity. See docs/architecture/implementation-plan.md's M2
section for the rationale. ``area_of_operation`` is kept as a real PostGIS
geometry column since spatial queries on it are an expected use case.

``scenario_versions`` rows are immutable once inserted: this is enforced by
convention in ``rogue.persistence.repository`` (no UPDATE/DELETE is ever
issued against this table), not by a database trigger, in this feature.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rogue.db.base import Base


class ScenarioORM(Base):
    """Stable scenario identity — see ``rogue.domain.scenario.Scenario``."""

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    coordinate_system: Mapped[str] = mapped_column(String, nullable=False)
    area_of_operation: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326), nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_versions.id", use_alter=True, name="fk_scenarios_current_version_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    drafts: Mapped[list[ScenarioDraftORM]] = relationship(
        back_populates="scenario", foreign_keys="ScenarioDraftORM.scenario_id"
    )
    versions: Mapped[list[ScenarioVersionORM]] = relationship(
        back_populates="scenario", foreign_keys="ScenarioVersionORM.scenario_id"
    )


class ScenarioDraftORM(Base):
    """Editable working copy — see ``rogue.domain.scenario.ScenarioDraft``."""

    __tablename__ = "scenario_drafts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    base_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenario_versions.id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    author: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    scenario: Mapped[ScenarioORM] = relationship(
        back_populates="drafts", foreign_keys=[scenario_id]
    )


class ScenarioVersionORM(Base):
    """Immutable published version — see ``rogue.domain.scenario.ScenarioVersion``."""

    __tablename__ = "scenario_versions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "version_number", name="uq_scenario_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    scenario: Mapped[ScenarioORM] = relationship(
        back_populates="versions", foreign_keys=[scenario_id]
    )


class IQRecordingORM(Base):
    """Immutable SigMF catalogue entry version — see ``rogue.domain.recording.IQRecording``.

    Rows are immutable once inserted, like ``scenario_versions``: no
    UPDATE/DELETE is ever issued against this table (see
    ``rogue.persistence.catalogue``). ``access_classification`` and
    ``provenance`` are duplicated out of ``document`` purely so the
    catalogue list endpoint can filter on them.
    """

    __tablename__ = "iq_recordings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    access_classification: Mapped[str] = mapped_column(String, nullable=False)
    provenance: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReplayPlanORM(Base):
    """Immutable compiled Replay Plan (M6) — see ``rogue.compiler.models.ReplayPlan``.

    Rows are immutable once inserted, like ``scenario_versions``/
    ``iq_recordings``: no UPDATE/DELETE is ever issued against this table.
    """

    __tablename__ = "replay_plans"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    scenario_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    compiler_version: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyKeyORM(Base):
    """Cached response for a replayed mutating request, keyed per endpoint."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
