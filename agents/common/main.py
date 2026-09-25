"""SDR Agent process entrypoint (M0 presence-only placeholder replaced in M8).

Process bootstrap/signal handling only — the actual command handling,
presence/telemetry publishing and local watchdog live in
``agents.common.agent.AgentRuntime`` (ADR-008). ``ROGUE_AGENT_DEVICE_IDS``
selects this process's slice of ``DEFAULT_CAPABILITY_PROFILE`` (docker-
compose.yml runs two Agent instances with disjoint slices, so the control
plane's device_id->agent_id registry lookup is actually exercised rather
than always resolving to the only agent that exists).

``ROGUE_AGENT_INGRESS`` (ADR-019, M19a) selects the command ingress(es):
``nats`` (default, unchanged) blocks on ``nats.connect()`` before this
process does anything else, exactly as before M19. ``local``/``both`` start
``agents.common.local_api``'s HTTP ingress and never block startup on NATS
reachability — a control-plane outage must not prevent a previously-
validated replay from running locally.

``ROGUE_AGENT_LOCAL_RECORDING_ROOT`` (ADR-019, M19b), if set, resolves
PREFLIGHT's recordings from that local SigMF root
(``agents.common.local_recording_source``) instead of MinIO — the other
half of running a replay with no control plane reachable at all.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import nats
import nats.errors
import uvicorn
from nats.aio.client import Client as NATSClient

from agents.common.agent import AgentRuntime
from agents.common.local_api import create_local_api
from rogue.compiler.models import DEFAULT_CAPABILITY_PROFILE, PhysicalTxChannelCapability

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rogue.agent")

# Bounded so a "local"/"both" ingress Agent starts promptly even when NATS is
# completely unreachable, rather than hanging on the library's own internal
# reconnect/backoff loop.
NATS_BEST_EFFORT_CONNECT_TIMEOUT_SECONDS = 5.0


class UnknownAgentIngressError(ValueError):
    """Raised when ``ROGUE_AGENT_INGRESS`` doesn't match a known ingress mode."""


def _capabilities_for_devices(device_ids: set[str]) -> list[PhysicalTxChannelCapability]:
    return [c for c in DEFAULT_CAPABILITY_PROFILE.channels if c.device_id in device_ids]


async def _connect_nats_best_effort(nats_url: str, agent_id: str) -> NATSClient | None:
    """Attempts a bounded, non-fatal NATS connection for ``local``/``both``
    ingress (ADR-019 item 4) — returns ``None`` instead of raising so a
    control-plane outage cannot prevent this process from starting or
    serving local commands.
    """
    try:
        return await asyncio.wait_for(
            nats.connect(nats_url), timeout=NATS_BEST_EFFORT_CONNECT_TIMEOUT_SECONDS
        )
    except (TimeoutError, OSError, nats.errors.Error) as exc:
        logger.warning(
            "agent_id=%s could not reach NATS at %s (%s); continuing with no "
            "control-plane connectivity",
            agent_id,
            nats_url,
            exc,
        )
        return None


async def _serve_local_api(
    runtime: AgentRuntime, host: str, port: int, stop: asyncio.Event
) -> None:
    app = create_local_api(runtime)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    serve_task = asyncio.create_task(server.serve())
    try:
        await stop.wait()
    finally:
        server.should_exit = True
        await serve_task


async def run() -> None:
    agent_id = os.environ.get("ROGUE_AGENT_ID", "sim-agent-unknown")
    mode = os.environ.get("ROGUE_AGENT_MODE", "simulated")
    nats_url = os.environ.get("ROGUE_NATS_URL", "nats://localhost:4222")
    cache_dir = Path(os.environ.get("ROGUE_AGENT_CACHE_DIR", f"/tmp/rogue-agent-cache/{agent_id}"))
    device_ids_env = os.environ.get("ROGUE_AGENT_DEVICE_IDS", "")
    device_ids = {d.strip() for d in device_ids_env.split(",") if d.strip()}
    capabilities = _capabilities_for_devices(device_ids) if device_ids else []
    ingress = os.environ.get("ROGUE_AGENT_INGRESS", "nats")
    if ingress not in ("nats", "local", "both"):
        raise UnknownAgentIngressError(f"unknown ROGUE_AGENT_INGRESS {ingress!r}")
    local_recording_root_env = os.environ.get("ROGUE_AGENT_LOCAL_RECORDING_ROOT")
    local_recording_root = Path(local_recording_root_env) if local_recording_root_env else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    nc: NATSClient | None
    if ingress == "nats":
        # Unchanged from before M19: NATS is the only ingress, so an
        # unreachable control plane must prevent this process from starting.
        nc = await nats.connect(nats_url)
    else:
        nc = await _connect_nats_best_effort(nats_url, agent_id)
    if nc is not None:
        logger.info(
            "agent_id=%s mode=%s connected to %s, owning %d channel(s)",
            agent_id,
            mode,
            nats_url,
            len(capabilities),
        )

    runtime = AgentRuntime(
        agent_id=agent_id,
        capabilities=capabilities,
        cache_dir=cache_dir,
        mode=mode,
        local_recording_root=local_recording_root,
    )

    local_api_task: asyncio.Task[None] | None = None
    if ingress in ("local", "both"):
        host = os.environ.get("ROGUE_AGENT_LOCAL_API_HOST", "127.0.0.1")
        port = int(os.environ.get("ROGUE_AGENT_LOCAL_API_PORT", "8600"))
        local_api_task = asyncio.create_task(_serve_local_api(runtime, host, port, stop))
        logger.info("agent_id=%s local command API listening on %s:%d", agent_id, host, port)

    try:
        await runtime.run(nc, stop)
    finally:
        if local_api_task is not None:
            await local_api_task
        if nc is not None:
            await nc.drain()
        logger.info("agent_id=%s disconnected", agent_id)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
