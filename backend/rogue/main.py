"""FastAPI application entrypoint for the ROGUE control-plane API.

M0 added the health endpoint; M2 adds the scenario draft/version/clone/
validation API. RF planning, replay and hardware-orchestration routers are
added in later milestones; see docs/architecture/implementation-plan.md for
the sequence.
"""

from __future__ import annotations

from fastapi import FastAPI

from rogue.api.errors import register_exception_handlers
from rogue.api.health import router as health_router
from rogue.api.scenarios import router as scenarios_router

app = FastAPI(title="ROGUE Control Plane API", version="0.1.0")
app.include_router(health_router)
app.include_router(scenarios_router)
register_exception_handlers(app)
