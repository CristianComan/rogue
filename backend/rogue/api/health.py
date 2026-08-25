"""Health-check endpoint.

Used by the Docker Compose healthcheck, CI smoke tests and operator
tooling to confirm the control-plane API process is up. It performs no
dependency checks (database/broker/storage) yet; that is expected to
follow once M2 (scenario persistence) introduces those dependencies.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthStatus(BaseModel):
    """Response body for GET /health."""

    status: str
    service: str


@router.get("/health", response_model=HealthStatus)
async def get_health() -> HealthStatus:
    """Report basic liveness of the control-plane API process."""
    return HealthStatus(status="ok", service="rogue-api")
