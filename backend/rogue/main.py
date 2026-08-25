"""FastAPI application entrypoint for the ROGUE control-plane API.

M0 scope: expose only a health endpoint so the Docker Compose stack and
CI pipeline can prove the service boots. Scenario, RF planning, replay
and hardware-orchestration routers are added in later milestones; see
docs/architecture/implementation-plan.md for the sequence.
"""

from __future__ import annotations

from fastapi import FastAPI

from rogue.api.health import router as health_router

app = FastAPI(title="ROGUE Control Plane API", version="0.1.0")
app.include_router(health_router)
