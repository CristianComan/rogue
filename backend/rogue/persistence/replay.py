"""Replay Plan compilation + persistence orchestration (M6).

Mirrors ``rogue.persistence.spectrum``'s shape: fetches a published
``ScenarioVersion`` (``repository.get_version``), batch-resolves referenced
recordings (``catalogue.get_recording``), and delegates to the pure
``rogue.compiler.compile.compile_replay_plan``. Unlike M5's read-only
``/spectrum`` endpoint, a successful compile is persisted as an immutable
``ReplayPlan`` row (same JSONB-document/never-UPDATE convention as
``scenario_versions``/``iq_recordings``) — a compile with BLOCKING findings
raises ``repository.CompilationRejectedError`` and persists nothing.

Lives in its own module for the same reason as ``rogue.persistence.
spectrum``: ``catalogue.py`` already imports ``repository.py``, so
``repository.py`` cannot import ``catalogue.py`` back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.compiler.compile import compile_replay_plan
from rogue.compiler.models import DEFAULT_CAPABILITY_PROFILE, HardwareCapabilityProfile, ReplayPlan
from rogue.db.models import ReplayPlanORM
from rogue.domain.recording import IQRecording
from rogue.domain.validation import ValidationSeverity
from rogue.persistence import catalogue, repository
from rogue.persistence.repository import CompilationRejectedError, NotFoundError
from rogue.spectrum.occupancy import RecordingKey


def _orm_to_plan(row: ReplayPlanORM) -> ReplayPlan:
    return ReplayPlan.model_validate(row.document)


async def compile_and_store_replay_plan(
    session: AsyncSession,
    scenario_id: UUID,
    version_number: int,
    duration_s: float,
    capability_profile: HardwareCapabilityProfile | None = None,
) -> ReplayPlan:
    """Compile ``scenario_id``'s published ``version_number`` and, if it has
    no BLOCKING findings, persist the result.

    Raises ``NotFoundError`` if the version doesn't exist,
    ``CompilationRejectedError`` (carrying the findings) if compilation is
    rejected. ``capability_profile`` defaults to
    ``rogue.compiler.models.DEFAULT_CAPABILITY_PROFILE`` when omitted.
    """
    version = await repository.get_version(session, scenario_id, version_number)
    if version is None:
        raise NotFoundError(f"scenario {scenario_id} has no version {version_number}")

    recording_keys: set[RecordingKey] = {
        (emission.recording.recording_id, emission.recording.version)
        for mission in version.missions
        for link in mission.rf_links
        for emission in link.emissions
        if emission.recording is not None
    }
    recordings: dict[RecordingKey, IQRecording] = {}
    for recording_id, recording_version in recording_keys:
        recording = await catalogue.get_recording(session, recording_id, recording_version)
        if recording is not None:
            recordings[(recording_id, recording_version)] = recording

    profile = capability_profile if capability_profile is not None else DEFAULT_CAPABILITY_PROFILE
    plan = compile_replay_plan(version, recordings, duration_s, profile)

    if any(f.severity == ValidationSeverity.BLOCKING for f in plan.findings):
        raise CompilationRejectedError(plan.findings)

    session.add(
        ReplayPlanORM(
            id=plan.id,
            scenario_id=scenario_id,
            scenario_version_number=version_number,
            compiler_version=plan.compiler_version,
            document=plan.model_dump(mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return plan


async def get_replay_plan(
    session: AsyncSession, scenario_id: UUID, plan_id: UUID
) -> ReplayPlan | None:
    row = await session.get(ReplayPlanORM, plan_id)
    if row is None or row.scenario_id != scenario_id:
        return None
    return _orm_to_plan(row)


async def list_replay_plans(session: AsyncSession, scenario_id: UUID) -> list[ReplayPlan]:
    stmt = (
        select(ReplayPlanORM)
        .where(ReplayPlanORM.scenario_id == scenario_id)
        .order_by(ReplayPlanORM.created_at)
    )
    result = await session.execute(stmt)
    return [_orm_to_plan(row) for row in result.scalars()]
