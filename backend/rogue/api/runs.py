"""Simulated ScenarioRun execution API (M7).

Mirrors ``rogue.api.replay``'s shape, nested under a compiled ReplayPlan:
create+prepare a run, then step it through arm/start/stop. Business logic
lives in ``rogue.persistence.run``; the underlying state machine is
``rogue.execution.orchestrator``, run in-process against a simulated adapter
(no NATS, no separate Agent process — that's M8).

``emergency-stop`` deliberately takes no request body, never 404s into an
unrecoverable state, and is not idempotency-key gated: it must always be
reachable and always succeed, per CLAUDE.md's safety rules.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.api.idempotency import replay_or_execute
from rogue.api.schemas import RunCreateRequest
from rogue.db.session import get_session
from rogue.domain.run import ScenarioRun
from rogue.persistence import repository
from rogue.persistence import run as run_persistence

router = APIRouter(prefix="/scenarios", tags=["runs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.post("/{scenario_id}/replay-plans/{plan_id}/runs", status_code=201)
async def create_run(
    scenario_id: UUID,
    plan_id: UUID,
    request: RunCreateRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        run = await run_persistence.create_and_prepare_run(
            session, scenario_id, plan_id, request.operator
        )
        return 201, run.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/replay-plans/{plan_id}/runs"
    status_code, body = await replay_or_execute(
        session, idempotency_key, endpoint, request.model_dump_json(), execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.post("/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/arm")
async def arm_run(
    scenario_id: UUID,
    plan_id: UUID,
    run_id: UUID,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        run = await run_persistence.arm_run(session, scenario_id, run_id)
        return 200, run.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/arm"
    status_code, body = await replay_or_execute(session, idempotency_key, endpoint, "", execute)
    return JSONResponse(status_code=status_code, content=body)


@router.post("/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/start")
async def start_run(
    scenario_id: UUID,
    plan_id: UUID,
    run_id: UUID,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        run = await run_persistence.start_run(session, scenario_id, run_id)
        return 200, run.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/start"
    status_code, body = await replay_or_execute(session, idempotency_key, endpoint, "", execute)
    return JSONResponse(status_code=status_code, content=body)


@router.post("/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/stop")
async def stop_run(
    scenario_id: UUID,
    plan_id: UUID,
    run_id: UUID,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        run = await run_persistence.stop_run(session, scenario_id, run_id)
        return 200, run.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/stop"
    status_code, body = await replay_or_execute(session, idempotency_key, endpoint, "", execute)
    return JSONResponse(status_code=status_code, content=body)


@router.post("/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}/emergency-stop")
async def emergency_stop_run(
    scenario_id: UUID, plan_id: UUID, run_id: UUID, session: SessionDep
) -> ScenarioRun:
    return await run_persistence.emergency_stop_run(session, scenario_id, run_id)


@router.get("/{scenario_id}/replay-plans/{plan_id}/runs/{run_id}", response_model=ScenarioRun)
async def get_run(
    scenario_id: UUID, plan_id: UUID, run_id: UUID, session: SessionDep
) -> ScenarioRun:
    run = await run_persistence.get_run(session, scenario_id, run_id)
    if run is None:
        raise repository.NotFoundError(f"run {run_id} does not exist on scenario {scenario_id}")
    return run


@router.get("/{scenario_id}/replay-plans/{plan_id}/runs", response_model=list[ScenarioRun])
async def list_runs(scenario_id: UUID, plan_id: UUID, session: SessionDep) -> list[ScenarioRun]:
    return await run_persistence.list_runs(session, scenario_id)
