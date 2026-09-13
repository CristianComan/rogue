"""RF spectrum planner API (M5).

Read-only computation over a draft, mirroring ``rogue.api.scenarios``'s
``validate_draft`` shape (no mutation, so no idempotency key needed).
Business logic lives in ``rogue.persistence.spectrum``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.api.schemas import SpectrumStateRequest
from rogue.db.session import get_session
from rogue.persistence import spectrum
from rogue.spectrum.models import SpectrumState

router = APIRouter(prefix="/scenarios", tags=["spectrum"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/{scenario_id}/drafts/{draft_id}/spectrum",
    response_model=SpectrumState,
)
async def get_spectrum_state(
    scenario_id: UUID, draft_id: UUID, request: SpectrumStateRequest, session: SessionDep
) -> SpectrumState:
    return await spectrum.spectrum_state_for_draft(
        session, scenario_id, draft_id, request.at_seconds
    )
