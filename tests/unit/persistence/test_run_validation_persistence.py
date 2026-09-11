"""Independent RF validation persistence tests (M14) against a real Postgres
(see conftest.py). Mirrors test_run_execution.py's shape."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from persistence_factories import make_draft, make_mission, make_recording, make_scenario
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.db.models import IQRecordingORM, ScenarioRunORM
from rogue.domain.common import GeoPoint
from rogue.domain.receiver import Receiver, ReceiverType
from rogue.domain.run import RunEventKind, RunStatus
from rogue.execution.orchestrator import InvalidRunTransitionError
from rogue.persistence import replay as replay_persistence
from rogue.persistence import repository
from rogue.persistence import run as run_persistence


async def _running_run(session: AsyncSession, *, with_monitor_receiver: bool = True):
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
    receivers = (
        [
            Receiver(
                name="rx-1",
                receiver_type=ReceiverType.MONITOR,
                position=GeoPoint(coordinates=(13.42, 52.50)),
            )
        ]
        if with_monitor_receiver
        else []
    )
    draft = make_draft(
        scenario.id, missions=[make_mission(ref)], recordings=[ref], receivers=receivers
    )
    await repository.create_draft(session, draft)
    version = await repository.publish_draft(session, scenario.id, draft.id)

    plan = await replay_persistence.compile_and_store_replay_plan(
        session, scenario.id, version.version_number, duration_s=20.0
    )
    run = await run_persistence.create_and_prepare_run(
        session, scenario.id, plan.id, operator="test-operator"
    )
    await run_persistence.arm_run(session, scenario.id, run.id)
    run = await run_persistence.start_run(session, scenario.id, run.id)
    assert run.status == RunStatus.RUNNING
    return scenario, plan, run


async def test_record_validation_appends_a_report_and_event(session: AsyncSession) -> None:
    scenario, plan, run = await _running_run(session)
    window = plan.rf_windows[0]
    at_seconds = (window.start_seconds + window.end_seconds) / 2

    validated = await run_persistence.record_validation(session, scenario.id, run.id, at_seconds)

    assert len(validated.validation_reports) == 1
    assert any(e.kind == RunEventKind.VALIDATION_RECORDED for e in validated.events)

    fetched = await run_persistence.get_run(session, scenario.id, run.id)
    assert fetched == validated


async def test_record_validation_missing_run_raises_not_found(session: AsyncSession) -> None:
    scenario, _plan, _run = await _running_run(session)

    with pytest.raises(repository.NotFoundError):
        await run_persistence.record_validation(session, scenario.id, uuid4(), at_seconds=1.0)


async def test_record_validation_on_a_created_run_raises_invalid_transition(
    session: AsyncSession,
) -> None:
    scenario, plan, run = await _running_run(session)
    # Force the persisted document back to CREATED to exercise the guard.
    row = await session.get(ScenarioRunORM, run.id)
    assert row is not None
    document = dict(row.document)
    document["status"] = "created"
    row.document = document
    await session.flush()

    with pytest.raises(InvalidRunTransitionError):
        await run_persistence.record_validation(session, scenario.id, run.id, at_seconds=1.0)
