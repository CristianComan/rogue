"""Scenario draft/version/clone/validation API (M2).

Business logic (validation orchestration, version numbering, optimistic
concurrency) lives in ``rogue.persistence.repository``; this module only
translates HTTP <-> domain calls and commits/rolls back the session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.api.idempotency import replay_or_execute
from rogue.api.schemas import (
    CloneRequest,
    CloneResponse,
    DraftCreateRequest,
    DraftUpdateRequest,
    ScenarioCreateRequest,
)
from rogue.db.session import get_session
from rogue.domain.scenario import Scenario, ScenarioDraft, ScenarioVersion
from rogue.domain.validation import ValidationFinding
from rogue.persistence import repository

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.post("", status_code=201)
async def create_scenario(
    request: ScenarioCreateRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        now = datetime.now(UTC)
        scenario = Scenario(
            id=uuid4(),
            name=request.name,
            owner=request.owner,
            tags=request.tags,
            coordinate_system=request.coordinate_system,
            area_of_operation=request.area_of_operation,
            variables=request.variables,
            created_at=now,
            updated_at=now,
        )
        created = await repository.create_scenario(session, scenario)
        return 201, created.model_dump(mode="json")

    status_code, body = await replay_or_execute(
        session, idempotency_key, "POST /scenarios", request.model_dump_json(), execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("", response_model=list[Scenario])
async def list_scenarios(
    session: SessionDep,
    owner: str | None = None,
    tag: str | None = None,
    name_contains: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Scenario]:
    return await repository.list_scenarios(
        session, owner=owner, tag=tag, name_contains=name_contains, limit=limit, offset=offset
    )


@router.get("/{scenario_id}", response_model=Scenario)
async def get_scenario(scenario_id: UUID, session: SessionDep) -> Scenario:
    scenario = await repository.get_scenario(session, scenario_id)
    if scenario is None:
        raise repository.NotFoundError(f"scenario {scenario_id} does not exist")
    return scenario


@router.post("/{scenario_id}/drafts", status_code=201)
async def create_draft(
    scenario_id: UUID,
    request: DraftCreateRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        now = datetime.now(UTC)
        draft = ScenarioDraft(
            id=uuid4(),
            scenario_id=scenario_id,
            base_version_id=request.base_version_id,
            revision=0,
            author=request.author,
            zones=request.zones,
            missions=request.missions,
            receivers=request.receivers,
            timeline_events=request.timeline_events,
            recordings=request.recordings,
            created_at=now,
            updated_at=now,
        )
        created = await repository.create_draft(session, draft)
        return 201, created.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/drafts"
    status_code, body = await replay_or_execute(
        session, idempotency_key, endpoint, request.model_dump_json(), execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("/{scenario_id}/drafts/{draft_id}", response_model=ScenarioDraft)
async def get_draft(scenario_id: UUID, draft_id: UUID, session: SessionDep) -> ScenarioDraft:
    draft = await repository.get_draft(session, scenario_id, draft_id)
    if draft is None:
        raise repository.NotFoundError(f"draft {draft_id} does not exist on scenario {scenario_id}")
    return draft


@router.put("/{scenario_id}/drafts/{draft_id}", response_model=ScenarioDraft)
async def update_draft(
    scenario_id: UUID, draft_id: UUID, request: DraftUpdateRequest, session: SessionDep
) -> ScenarioDraft:
    existing = await repository.get_draft(session, scenario_id, draft_id)
    if existing is None:
        raise repository.NotFoundError(f"draft {draft_id} does not exist on scenario {scenario_id}")

    updated = existing.model_copy(
        update={
            "author": request.author,
            "zones": request.zones,
            "missions": request.missions,
            "receivers": request.receivers,
            "timeline_events": request.timeline_events,
            "recordings": request.recordings,
        }
    )
    saved = await repository.update_draft(
        session, scenario_id, draft_id, updated, request.expected_revision
    )
    await session.commit()
    return saved


@router.post("/{scenario_id}/drafts/{draft_id}/validate", response_model=list[ValidationFinding])
async def validate_draft(
    scenario_id: UUID, draft_id: UUID, session: SessionDep
) -> list[ValidationFinding]:
    return await repository.validate_draft(session, scenario_id, draft_id)


@router.post("/{scenario_id}/drafts/{draft_id}/publish", status_code=201)
async def publish_draft(
    scenario_id: UUID,
    draft_id: UUID,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        published = await repository.publish_draft(session, scenario_id, draft_id)
        return 201, published.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/drafts/{draft_id}/publish"
    status_code, body = await replay_or_execute(session, idempotency_key, endpoint, "", execute)
    return JSONResponse(status_code=status_code, content=body)


@router.get("/{scenario_id}/versions", response_model=list[ScenarioVersion])
async def list_versions(scenario_id: UUID, session: SessionDep) -> list[ScenarioVersion]:
    return await repository.list_versions(session, scenario_id)


@router.get("/{scenario_id}/versions/{version_number}", response_model=ScenarioVersion)
async def get_version(
    scenario_id: UUID, version_number: int, session: SessionDep
) -> ScenarioVersion:
    version = await repository.get_version(session, scenario_id, version_number)
    if version is None:
        raise repository.NotFoundError(f"scenario {scenario_id} has no version {version_number}")
    return version


@router.post("/{scenario_id}/clone", status_code=201)
async def clone_scenario(
    scenario_id: UUID,
    request: CloneRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        new_scenario, new_draft = await repository.clone_scenario(
            session,
            scenario_id,
            name=request.name,
            owner=request.owner,
            source_version_number=request.source_version_number,
        )
        response = CloneResponse(scenario_id=new_scenario.id, draft_id=new_draft.id)
        return 201, response.model_dump(mode="json")

    endpoint = f"POST /scenarios/{scenario_id}/clone"
    status_code, body = await replay_or_execute(
        session, idempotency_key, endpoint, request.model_dump_json(), execute
    )
    return JSONResponse(status_code=status_code, content=body)
