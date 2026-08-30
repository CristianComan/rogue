"""FastAPI application entrypoint for the ROGUE control-plane API.

M0 added the health endpoint; M2 added the scenario draft/version/clone/
validation API; M4 added the SigMF recording catalogue API. RF planning,
replay and hardware-orchestration routers are added in later milestones; see
docs/architecture/implementation-plan.md for the sequence.

CORS is scoped to ``settings.cors_allowed_origins`` (the M3 Vite dev server
by default) — the control-plane API is reached from an operator's browser,
per system-design.md §8's "isolated test network by default," not opened
broadly.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rogue.api.errors import register_exception_handlers
from rogue.api.health import router as health_router
from rogue.api.recordings import router as recordings_router
from rogue.api.scenarios import router as scenarios_router
from rogue.settings import settings

app = FastAPI(title="ROGUE Control Plane API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(scenarios_router)
app.include_router(recordings_router)
register_exception_handlers(app)
