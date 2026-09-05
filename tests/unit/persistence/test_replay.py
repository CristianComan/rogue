"""Replay Plan persistence tests against a real Postgres (see conftest.py).

Inserts an IQRecordingORM row directly rather than going through
``catalogue.ingest_recording`` — mirrors test_spectrum.py's rationale.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from persistence_factories import make_draft, make_mission, make_recording, make_scenario
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.db.models import IQRecordingORM
from rogue.persistence import replay as replay_persistence
from rogue.persistence import repository


async def _publish_version(session: AsyncSession, **draft_overrides: object):
    scenario = await repository.create_scenario(session, make_scenario())
    draft = make_draft(scenario.id, **draft_overrides)
    await repository.create_draft(session, draft)
    version = await repository.publish_draft(session, scenario.id, draft.id)
    return scenario, version


async def test_compile_and_store_replay_plan_persists_a_plan(session: AsyncSession) -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=100.0)
    session.add(
        IQRecordingORM(
            id=recording.id,
            version=recording.version,
            document=recording.model_dump(mode="json"),
            access_classification=recording.access_classification.value,
            provenance=None,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()

    ref = recording.reference()
    scenario, version = await _publish_version(
        session, missions=[make_mission(ref)], recordings=[ref]
    )

    plan = await replay_persistence.compile_and_store_replay_plan(
        session, scenario.id, version.version_number, duration_s=20.0
    )

    assert plan.scenario_id == scenario.id
    assert plan.scenario_version_number == version.version_number
    assert len(plan.rf_windows) == 1

    fetched = await replay_persistence.get_replay_plan(session, scenario.id, plan.id)
    assert fetched == plan

    listed = await replay_persistence.list_replay_plans(session, scenario.id)
    assert [p.id for p in listed] == [plan.id]


async def test_compile_missing_version_raises_not_found(session: AsyncSession) -> None:
    scenario = await repository.create_scenario(session, make_scenario())

    with pytest.raises(repository.NotFoundError):
        await replay_persistence.compile_and_store_replay_plan(
            session, scenario.id, 1, duration_s=10.0
        )


async def test_compile_infeasible_bandwidth_raises_compilation_rejected_and_persists_nothing(
    session: AsyncSession,
) -> None:
    recording = make_recording(sample_rate_hz=50_000_000.0, duration_s=100.0)
    session.add(
        IQRecordingORM(
            id=recording.id,
            version=recording.version,
            document=recording.model_dump(mode="json"),
            access_classification=recording.access_classification.value,
            provenance=None,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()

    ref = recording.reference()
    scenario, version = await _publish_version(
        session, missions=[make_mission(ref)], recordings=[ref]
    )

    with pytest.raises(repository.CompilationRejectedError) as exc_info:
        await replay_persistence.compile_and_store_replay_plan(
            session, scenario.id, version.version_number, duration_s=10.0
        )
    assert exc_info.value.findings

    listed = await replay_persistence.list_replay_plans(session, scenario.id)
    assert listed == []


async def test_get_replay_plan_missing_returns_none(session: AsyncSession) -> None:
    scenario = await repository.create_scenario(session, make_scenario())

    assert await replay_persistence.get_replay_plan(session, scenario.id, uuid4()) is None
