"""ScenarioRun lifecycle persistence tests against a real Postgres (see conftest.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from persistence_factories import make_draft, make_mission, make_recording, make_scenario
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.db.models import IQRecordingORM, ScenarioRunORM
from rogue.domain.run import RunStatus
from rogue.execution.orchestrator import InvalidRunTransitionError
from rogue.persistence import replay as replay_persistence
from rogue.persistence import repository
from rogue.persistence import run as run_persistence


async def _compiled_plan(session: AsyncSession):
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
    scenario = await repository.create_scenario(session, make_scenario())
    draft = make_draft(scenario.id, missions=[make_mission(ref)], recordings=[ref])
    await repository.create_draft(session, draft)
    version = await repository.publish_draft(session, scenario.id, draft.id)

    plan = await replay_persistence.compile_and_store_replay_plan(
        session, scenario.id, version.version_number, duration_s=20.0
    )
    return scenario, plan


async def test_create_and_prepare_run_persists_a_prepared_run(session: AsyncSession) -> None:
    scenario, plan = await _compiled_plan(session)

    run = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="test-operator"
    )

    assert run.status == RunStatus.PREPARED
    assert run.scenario_id == scenario.id
    assert run.replay_plan_id == plan.id

    fetched = await run_persistence.get_run(session, scenario.id, run.id)
    assert fetched == run


async def test_create_and_prepare_run_missing_plan_raises_not_found(session: AsyncSession) -> None:
    scenario = await repository.create_scenario(session, make_scenario())

    with pytest.raises(repository.NotFoundError):
        await run_persistence.create_and_prepare_run(
            session, scenario.id, uuid4(), operator="test-operator"
        )


async def test_full_lifecycle_grows_events_and_advances_status(session: AsyncSession) -> None:
    scenario, plan = await _compiled_plan(session)
    run = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="test-operator"
    )

    armed = await run_persistence.arm_run(session, scenario.id, run.id)
    assert armed.status == RunStatus.ARMED
    assert len(armed.events) > len(run.events)

    started = await run_persistence.start_run(session, scenario.id, run.id)
    assert started.status == RunStatus.RUNNING
    assert len(started.events) > len(armed.events)

    stopped = await run_persistence.stop_run(session, scenario.id, run.id)
    assert stopped.status == RunStatus.STOPPED
    assert len(stopped.events) > len(started.events)

    fetched = await run_persistence.get_run(session, scenario.id, run.id)
    assert fetched == stopped


async def test_arm_run_on_a_run_still_in_created_status_raises_invalid_transition(
    session: AsyncSession,
) -> None:
    scenario, plan = await _compiled_plan(session)
    run = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="test-operator"
    )
    # Force the persisted document back to CREATED to exercise the guard.
    row = await session.get(ScenarioRunORM, run.id)
    assert row is not None
    document = dict(row.document)
    document["status"] = "created"
    row.document = document
    await session.flush()

    with pytest.raises(InvalidRunTransitionError):
        await run_persistence.arm_run(session, scenario.id, run.id)


async def test_emergency_stop_is_reachable_from_running(session: AsyncSession) -> None:
    scenario, plan = await _compiled_plan(session)
    run = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="test-operator"
    )
    await run_persistence.arm_run(session, scenario.id, run.id)
    await run_persistence.start_run(session, scenario.id, run.id)

    stopped = await run_persistence.emergency_stop_run(session, scenario.id, run.id)

    assert stopped.status == RunStatus.EMERGENCY_STOPPED


async def test_list_runs_orders_by_creation(session: AsyncSession) -> None:
    scenario, plan = await _compiled_plan(session)
    first = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="operator-a"
    )
    second = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="operator-b"
    )

    listed = await run_persistence.list_runs(session, scenario.id)

    assert [r.id for r in listed] == [first.id, second.id]


async def test_get_run_missing_returns_none(session: AsyncSession) -> None:
    scenario = await repository.create_scenario(session, make_scenario())

    assert await run_persistence.get_run(session, scenario.id, uuid4()) is None
