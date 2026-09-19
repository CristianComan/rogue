"""SDR Agent process entrypoint (M0 presence-only placeholder replaced in M8).

Process bootstrap/signal handling only — the actual command handling,
presence/telemetry publishing and local watchdog live in
``agents.common.agent.AgentRuntime`` (ADR-008). ``ROGUE_AGENT_DEVICE_IDS``
selects this process's slice of ``DEFAULT_CAPABILITY_PROFILE`` (docker-
compose.yml runs two Agent instances with disjoint slices, so the control
plane's device_id->agent_id registry lookup is actually exercised rather
than always resolving to the only agent that exists).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import nats

from agents.common.agent import AgentRuntime
from rogue.compiler.models import DEFAULT_CAPABILITY_PROFILE, PhysicalTxChannelCapability

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rogue.agent")


def _capabilities_for_devices(device_ids: set[str]) -> list[PhysicalTxChannelCapability]:
    return [c for c in DEFAULT_CAPABILITY_PROFILE.channels if c.device_id in device_ids]


async def run() -> None:
    agent_id = os.environ.get("ROGUE_AGENT_ID", "sim-agent-unknown")
    mode = os.environ.get("ROGUE_AGENT_MODE", "simulated")
    nats_url = os.environ.get("ROGUE_NATS_URL", "nats://localhost:4222")
    cache_dir = Path(os.environ.get("ROGUE_AGENT_CACHE_DIR", f"/tmp/rogue-agent-cache/{agent_id}"))
    device_ids_env = os.environ.get("ROGUE_AGENT_DEVICE_IDS", "")
    device_ids = {d.strip() for d in device_ids_env.split(",") if d.strip()}
    capabilities = _capabilities_for_devices(device_ids) if device_ids else []

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    nc = await nats.connect(nats_url)
    logger.info(
        "agent_id=%s mode=%s connected to %s, owning %d channel(s)",
        agent_id,
        mode,
        nats_url,
        len(capabilities),
    )
    runtime = AgentRuntime(
        agent_id=agent_id, capabilities=capabilities, cache_dir=cache_dir, mode=mode
    )
    try:
        await runtime.run(nc, stop)
    finally:
        await nc.drain()
        logger.info("agent_id=%s disconnected", agent_id)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
