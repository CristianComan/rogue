"""Agent inventory API (M8) — the "agent inventory" endpoint
``system-design.md`` line 94 names. Read-only: presence upserts happen via
the NATS subscriber started from the app lifespan
(``rogue.execution.presence``), not through this router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.db.session import get_session
from rogue.domain.agent import SDRAgentRecord
from rogue.persistence import agents as agents_persistence
from rogue.persistence.repository import NotFoundError

router = APIRouter(prefix="/agents", tags=["agents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[SDRAgentRecord])
async def list_agents(session: SessionDep) -> list[SDRAgentRecord]:
    return await agents_persistence.list_agents(session)


@router.get("/{agent_id}", response_model=SDRAgentRecord)
async def get_agent(agent_id: str, session: SessionDep) -> SDRAgentRecord:
    record = await agents_persistence.get_agent(session, agent_id)
    if record is None:
        raise NotFoundError(f"agent {agent_id} is not known to the control plane")
    return record
