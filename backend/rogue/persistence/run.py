"""ScenarioRun lifecycle persistence (M7, dispatch wiring extended in M8).

Mirrors ``rogue.persistence.replay``'s shape: fetches the immutable
``ReplayPlan`` and resolves the ``IQRecording``s its ``recording_manifest``
pins, then delegates the actual state transition to the pure
``rogue.execution.orchestrator`` functions. Unlike ``ReplayPlanORM``,
``ScenarioRunORM`` is mutable — each lifecycle call here is a
read-current-document, call-the-orchestrator, write-the-updated-document
round trip, the same shape as ``repository.update_draft`` minus optimistic-
concurrency revision checking (a run is orchestrator-driven, not
concurrently hand-edited — see ADR-007).

Which ``SDRAdapter`` implementation every run in this process talks to is
one module-level singleton, matching M7's "one simulated Agent for the
whole API process" granularity (docker-compose.yml's single
``simulated-agent`` service). By default (``settings.agent_dispatch_mode ==
"in_process"``) it's an in-process ``MockSDRAdapter`` — this is what every
unit test exercises, unchanged since M7. ``rogue.execution.lifespan`` calls
``configure_distributed_dispatch`` at API startup when
``ROGUE_AGENT_DISPATCH_MODE=distributed`` (docker-compose's real path),
swapping it for a ``RemoteAgentAdapter`` that dispatches over NATS to a
real, separate Agent process instead (ADR-008).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from nats.aio.client import Client as NATSClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rogue.compiler.models import (
    DEFAULT_CAPABILITY_PROFILE,
    PhysicalTxChannelCapability,
    ReplayPlan,
)
from rogue.db.models import ScenarioRunORM
from rogue.domain.recording import IQRecording
from rogue.domain.run import RunStatus, ScenarioRun
from rogue.execution import orchestrator
from rogue.execution.adapter import MockSDRAdapter, SDRAdapter
from rogue.execution.remote_adapter import RemoteAgentAdapter
from rogue.persistence import agents as agents_persistence
from rogue.persistence import catalogue
from rogue.persistence import replay as replay_persistence
from rogue.persistence.repository import NotFoundError

logger = logging.getLogger("rogue.persistence.run")

_ADAPTER: SDRAdapter = MockSDRAdapter(capabilities=DEFAULT_CAPABILITY_PROFILE.channels)


def configure_distributed_dispatch(
    nc: NATSClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Switch every subsequent run in this process to dispatch over NATS.

    Called once from ``rogue.execution.lifespan`` at API startup when
    ``settings.agent_dispatch_mode == "distributed"``. ``agent_lookup``/
    ``capabilities_lookup`` open their own short-lived session per call
    rather than reusing one across the adapter's lifetime, matching how
    every other read in this module is request/call-scoped.
    """

    async def agent_lookup(device_id: str) -> str | None:
        async with session_factory() as session:
            return await agents_persistence.get_agent_for_device(session, device_id)

    async def capabilities_lookup() -> list[PhysicalTxChannelCapability]:
        async with session_factory() as session:
            records = await agents_persistence.list_agents(session)
        return [channel for record in records for channel in record.capabilities]

    global _ADAPTER
    _ADAPTER = RemoteAgentAdapter(nc, agent_lookup, capabilities_lookup)


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
    prepared = await orchestrator.prepare_run(run, plan, recordings, _ADAPTER)
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

    advanced = await step(run, plan, _ADAPTER)
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


async def emergency_stop_run(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRun:
    return await _advance(session, scenario_id, run_id, orchestrator.emergency_stop_run)


async def renew_run_leases(session: AsyncSession, scenario_id: UUID, run_id: UUID) -> ScenarioRun:
    """Called by ``rogue.execution.lease_sweep`` on a short interval for
    every ARMED/RUNNING run — the central half of lease enforcement
    (ADR-008)."""
    return await _advance(session, scenario_id, run_id, orchestrator.renew_leases)


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


async def list_active_runs(session: AsyncSession) -> list[tuple[UUID, ScenarioRun]]:
    """Every run currently ARMED or RUNNING, across all scenarios — what
    ``rogue.execution.lease_sweep`` needs to sweep on each tick. Filtered in
    Python rather than a JSONB status query: the expected number of
    concurrently active runs in this milestone's lab/demo scale doesn't
    warrant an indexed status column (a reasonable future addition if that
    changes).

    Skips (with a logged warning) any row that fails to validate against
    the current ``ScenarioRun`` shape rather than raising — a stray
    pre-M8 document (a lease with no ``expires_at``) must not block
    sweeping every other active run.
    """
    result = await session.execute(select(ScenarioRunORM))
    active = (RunStatus.ARMED, RunStatus.RUNNING)
    active_runs: list[tuple[UUID, ScenarioRun]] = []
    for row in result.scalars():
        try:
            run = _orm_to_run(row)
        except ValidationError:
            logger.warning("skipping run %s: does not validate against the current schema", row.id)
            continue
        if run.status in active:
            active_runs.append((row.scenario_id, run))
    return active_runs
