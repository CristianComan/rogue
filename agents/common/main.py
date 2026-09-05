"""Minimal simulated SDR Agent process.

M0 scope: prove that an Agent process can start, connect to the NATS
control-plane broker, and publish a presence heartbeat. It does not yet
implement device discovery, leases, configuration or replay — see
docs/architecture/sdr-architecture.md and the M7/M8 milestones in
docs/architecture/implementation-plan.md for that work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import UTC, datetime

import nats
from nats.aio.client import Client as NATSClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rogue.agent")

PRESENCE_SUBJECT = "rogue.agents.presence"
HEARTBEAT_INTERVAL_SECONDS = 5.0


async def _heartbeat_loop(nc: NATSClient, agent_id: str, mode: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        payload = (
            f'{{"agent_id": "{agent_id}", "mode": "{mode}", '
            f'"timestamp": "{datetime.now(UTC).isoformat()}"}}'
        ).encode()
        await nc.publish(PRESENCE_SUBJECT, payload)
        logger.info("published presence heartbeat for agent_id=%s mode=%s", agent_id, mode)
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
        except TimeoutError:
            continue


async def run() -> None:
    agent_id = os.environ.get("ROGUE_AGENT_ID", "sim-agent-unknown")
    mode = os.environ.get("ROGUE_AGENT_MODE", "simulated")
    nats_url = os.environ.get("ROGUE_NATS_URL", "nats://localhost:4222")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    nc = await nats.connect(nats_url)
    logger.info("agent_id=%s mode=%s connected to %s", agent_id, mode, nats_url)
    try:
        await _heartbeat_loop(nc, agent_id, mode, stop)
    finally:
        await nc.drain()
        logger.info("agent_id=%s disconnected", agent_id)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
