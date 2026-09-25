"""Local HTTP command ingress for the Agent process (ADR-019, M19a).

A second, equally first-class command ingress alongside the NATS path
(`sdr-architecture.md` §4): `submit_command` below translates a request
directly into the same `AgentCommand`/`AgentAck` round trip
`agents.common.agent.AgentRuntime.handle_command` already answers on the
NATS command subject (ADR-008). No new command semantics are introduced
here — a request's `command_id` is simply carried as `AgentCommand`'s
existing `correlation_id`, so retries/idempotency behave exactly as they do
on the NATS path today.

`main.py` is responsible for binding this app to loopback or a management
interface only (`ROGUE_AGENT_LOCAL_API_HOST`) — this module has no opinion
on network exposure, it only builds the app.
"""

from __future__ import annotations

from fastapi import FastAPI

from agents.common.agent import AgentRuntime
from rogue.protocol.messages import AgentAck, AgentCommand


def create_local_api(runtime: AgentRuntime) -> FastAPI:
    """Builds a FastAPI app that dispatches commands into `runtime`.

    One app per Agent process, bound to one already-constructed
    `AgentRuntime` — there is no per-request Agent selection, matching the
    NATS path where a command's subject already picks the Agent.
    """
    app = FastAPI(title="ROGUE Agent Local Command API", version="1.0")

    @app.post("/commands", response_model=AgentAck)
    async def submit_command(command: AgentCommand) -> AgentAck:
        return await runtime.handle_command(command)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"agent_id": runtime.agent_id, "mode": runtime.mode}

    return app
