"""Tests for the central lease-sweep task (M8, ADR-008) against a real
Postgres. Uses its own connection/savepoint fixture (mirroring
tests/unit/api/conftest.py's ``client``/``connection`` pair) rather than the
plain ``session`` fixture, since ``lease_sweep.sweep_once`` opens several
short-lived sessions from a factory — the same shape it runs with in
production, not a single request-scoped session.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from persistence_factories import make_draft, make_mission, make_recording, make_scenario
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from rogue.db.models import IQRecordingORM, ScenarioRunORM
from rogue.db.session import engine
from rogue.domain.run import RunEventKind, RunStatus
from rogue.execution import lease_sweep
from rogue.persistence import replay as replay_persistence
from rogue.persistence import repository
from rogue.persistence import run as run_persistence


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()


@pytest_asyncio.fixture
def session_factory(connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


async def _armed_run(session_factory: async_sessionmaker[AsyncSession]) -> tuple:
    async with session_factory() as session:
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

        run = await run_persistence.create_and_prepare_run(
            session, scenario.id, plan.id, operator="test-operator"
        )
        armed = await run_persistence.arm_run(session, scenario.id, run.id)
        await session.commit()
        return scenario.id, armed


async def test_sweep_renews_leases_of_an_armed_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scenario_id, armed = await _armed_run(session_factory)
    original_expiries = {lease.id: lease.expires_at for lease in armed.device_leases}

    await lease_sweep.sweep_once(session_factory)

    async with session_factory() as session:
        renewed = await run_persistence.get_run(session, scenario_id, armed.id)
    assert renewed is not None
    assert renewed.status == RunStatus.ARMED
    assert renewed.events[-1].kind == RunEventKind.LEASE_RENEWED
    for lease in renewed.device_leases:
        assert lease.expires_at > original_expiries[lease.id]


async def test_sweep_emergency_stops_a_run_with_an_expired_lease(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scenario_id, armed = await _armed_run(session_factory)

    # Simulate time having passed without a renewal reaching this run: back-date
    # every lease's expires_at directly in the stored document. Mutates a
    # deep copy, not row.document in place — SQLAlchemy's change tracking
    # compares the new value against the very object it already holds, so
    # mutating that object first would make old == new and the UPDATE would
    # be skipped on flush.
    async with session_factory() as session:
        row = await session.get(ScenarioRunORM, armed.id)
        assert row is not None
        document = copy.deepcopy(row.document)
        expired_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        for lease in document["device_leases"]:
            lease["expires_at"] = expired_at
        row.document = document
        await session.commit()

    await lease_sweep.sweep_once(session_factory)

    async with session_factory() as session:
        stopped = await run_persistence.get_run(session, scenario_id, armed.id)
    assert stopped is not None
    assert stopped.status == RunStatus.EMERGENCY_STOPPED


async def test_sweep_leaves_a_stopped_run_untouched(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scenario_id, armed = await _armed_run(session_factory)
    async with session_factory() as session:
        stopped = await run_persistence.stop_run(session, scenario_id, armed.id)
        await session.commit()

    await lease_sweep.sweep_once(session_factory)

    async with session_factory() as session:
        fetched = await run_persistence.get_run(session, scenario_id, armed.id)
    assert fetched == stopped
