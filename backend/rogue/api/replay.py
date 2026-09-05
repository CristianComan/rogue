"""Replay Plan compiler API (M6).

Compiles a published, immutable ScenarioVersion into a persisted, immutable
ReplayPlan. Mirrors ``rogue.api.scenarios``'s publish/idempotency-key shape
(compilation is a creating, side-effectful POST, unlike M5's read-only
``/spectrum`` endpoint) — business logic lives in ``rogue.persistence.replay``.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.api.idempotency import replay_or_execute
from rogue.api.schemas import CompileRequest
from rogue.compiler.models import ReplayPlan
from rogue.db.session import get_session
from rogue.persistence import replay as replay_persistence
from rogue.persistence import repository

router = APIRouter(prefix="/scenarios", tags=["replay-plan"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.post("/{scenario_id}/versions/{version_number}/compile", status_code=201)
async def compile_scenario_version(
    scenario_id: UUID,
    version_number: int,
    request: CompileRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        plan = await replay_persistence.compile_and_store_replay_plan(
            session,
            scenario_id,
            version_number,
            request.duration_s,
            request.capability_profile,
        )
        return 201, plan.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/versions/{version_number}/compile"
    status_code, body = await replay_or_execute(
        session, idempotency_key, endpoint, request.model_dump_json(), execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("/{scenario_id}/replay-plans", response_model=list[ReplayPlan])
async def list_replay_plans(scenario_id: UUID, session: SessionDep) -> list[ReplayPlan]:
    return await replay_persistence.list_replay_plans(session, scenario_id)


@router.get("/{scenario_id}/replay-plans/{plan_id}", response_model=ReplayPlan)
async def get_replay_plan(scenario_id: UUID, plan_id: UUID, session: SessionDep) -> ReplayPlan:
    plan = await replay_persistence.get_replay_plan(session, scenario_id, plan_id)
    if plan is None:
        raise repository.NotFoundError(
            f"replay plan {plan_id} does not exist on scenario {scenario_id}"
        )
    return plan
