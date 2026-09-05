"""ScenarioRun lifecycle persistence (M7).

Mirrors ``rogue.persistence.replay``'s shape: fetches the immutable
``ReplayPlan`` and resolves the ``IQRecording``s its ``recording_manifest``
pins, then delegates the actual state transition to the pure
``rogue.execution.orchestrator`` functions. Unlike ``ReplayPlanORM``,
``ScenarioRunORM`` is mutable — each lifecycle call here is a
read-current-document, call-the-orchestrator, write-the-updated-document
round trip, the same shape as ``repository.update_draft`` minus optimistic-
concurrency revision checking (a run is orchestrator-driven, not
concurrently hand-edited — see ADR-007).

A single process-wide ``MockSDRAdapter`` is used for all runs in this
process: M7 is in-process simulated execution only (no NATS, no separate
Agent process — see ``rogue.execution.__init__``), so "one simulated Agent"
for the whole API process is the right granularity, matching
docker-compose.yml's single ``simulated-agent`` service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.compiler.models import DEFAULT_CAPABILITY_PROFILE, ReplayPlan
from rogue.db.models import ScenarioRunORM
from rogue.domain.recording import IQRecording
from rogue.domain.run import ScenarioRun
from rogue.execution import orchestrator
from rogue.execution.adapter import MockSDRAdapter, SDRAdapter
from rogue.persistence import catalogue
from rogue.persistence import replay as replay_persistence
from rogue.persistence.repository import NotFoundError

_SIMULATED_ADAPTER: SDRAdapter = MockSDRAdapter(capabilities=DEFAULT_CAPABILITY_PROFILE.channels)


def _orm_to_run(row: ScenarioRunORM) -> ScenarioRun:
    return ScenarioRun.model_validate(row.document)


async def _get_plan(session: AsyncSession, scenario_id: UUID, plan_id: UUID) -> ReplayPlan:
    plan = await replay_persistence.get_replay_plan(session, scenario_id, plan_id)
    if plan is None:
        raise NotFoundError(f"replay plan {plan_id} does not exist on scenario {scenario_id}")
    return plan


async def _resolve_recordings(
    session: AsyncSession, plan: ReplayPlan
) -> dict[tuple[UUID, int], IQRecording]:
    recordings: dict[tuple[UUID, int], IQRecording] = {}
    for entry in plan.recording_manifest:
        recording = await catalogue.get_recording(session, entry.recording_id, entry.version)
        if recording is not None:
            recordings[(entry.recording_id, entry.version)] = recording
    return recordings


async def create_and_prepare_run(
    session: AsyncSession, scenario_id: UUID, plan_id: UUID, operator: str
) -> ScenarioRun:
    plan = await _get_plan(session, scenario_id, plan_id)
    recordings = await _resolve_recordings(session, plan)

    run = ScenarioRun(scenario_id=scenario_id, replay_plan_id=plan_id, operator=operator)
    prepared = await orchestrator.prepare_run(run, plan, recordings, _SIMULATED_ADAPTER)
    prepared = prepared.model_copy(update={"updated_at": datetime.now(UTC)})

    session.add(
        ScenarioRunORM(
            id=prepared.id,
            scenario_id=scenario_id,
            replay_plan_id=plan_id,
            document=prepared.model_dump(mode="json"),
            created_at=prepared.created_at,
            updated_at=prepared.updated_at,
        )
    )
    await session.flush()
    return prepared


async def _get_run_row(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRunORM:
    row = await session.get(ScenarioRunORM, run_id)
    if row is None or row.scenario_id != scenario_id:
        raise NotFoundError(f"run {run_id} does not exist on scenario {scenario_id}")
    return row


_LifecycleStep = Callable[[ScenarioRun, ReplayPlan, SDRAdapter], Awaitable[ScenarioRun]]


async def _advance(
    session: AsyncSession,
    scenario_id: UUID,
    run_id: UUID,
    step: _LifecycleStep,
) -> ScenarioRun:
    row = await _get_run_row(session, scenario_id, run_id)
    run = _orm_to_run(row)
    plan = await _get_plan(session, scenario_id, run.replay_plan_id)

    advanced = await step(run, plan, _SIMULATED_ADAPTER)
    advanced = advanced.model_copy(update={"updated_at": datetime.now(UTC)})

    row.document = advanced.model_dump(mode="json")
    row.updated_at = advanced.updated_at
    await session.flush()
    return advanced


async def arm_run(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRun:
    return await _advance(session, scenario_id, run_id, orchestrator.arm_run)


async def start_run(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRun:
    return await _advance(session, scenario_id, run_id, orchestrator.start_run)


async def stop_run(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRun:
    return await _advance(session, scenario_id, run_id, orchestrator.stop_run)


async def emergency_stop_run(
    session: AsyncSession, scenario_id: UUID, run_id: UUID
) -> ScenarioRun:
    return await _advance(session, scenario_id, run_id, orchestrator.emergency_stop_run)


async def get_run(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRun | None:
    row = await session.get(ScenarioRunORM, run_id)
    if row is None or row.scenario_id != scenario_id:
        return None
    return _orm_to_run(row)


async def list_runs(session: AsyncSession, scenario_id: UUID) -> list[ScenarioRun]:
    stmt = (
        select(ScenarioRunORM)
        .where(ScenarioRunORM.scenario_id == scenario_id)
        .order_by(ScenarioRunORM.created_at)
    )
    result = await session.execute(stmt)
    return [_orm_to_run(row) for row in result.scalars()]
