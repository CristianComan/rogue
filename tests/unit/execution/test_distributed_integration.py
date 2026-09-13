"""End-to-end wire round trip: a real `AgentRuntime` behind a real NATS
broker, driven through `RemoteAgentAdapter` (M8, ADR-008).

Marked `nats` and skipped automatically when `nats://localhost:4222` isn't
reachable — every other test in this suite runs broker-free
(`test_remote_adapter.py`'s fake transport), per CLAUDE.md §10's "default
to simulation." This one test exists specifically to prove the
`AgentCommand`/`AgentAck` JSON wire format actually round-trips end to end,
which a fake transport can't demonstrate by construction.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import nats
import pytest
import pytest_asyncio
from agents.common.agent import AgentRuntime
from nats.aio.client import Client as NATSClient

from rogue.compiler.models import PhysicalTxChannelCapability, RfWindow
from rogue.execution.remote_adapter import RemoteAgentAdapter

pytestmark = pytest.mark.nats

DEVICE = "sim-1"
CHANNEL = 0
AGENT_ID = "test-integration-agent"


@pytest_asyncio.fixture
async def nc() -> AsyncIterator[NATSClient]:
    try:
        connection = await asyncio.wait_for(nats.connect("nats://localhost:4222"), timeout=2.0)
    except Exception:
        pytest.skip("nats://localhost:4222 is not reachable")
    yield connection
    await connection.drain()


def _capabilities() -> list[PhysicalTxChannelCapability]:
    return [
        PhysicalTxChannelCapability(
            device_id=DEVICE,
            channel_index=CHANNEL,
            device_family="simulated_generic",
            tunable_ranges_hz=[(1e6, 6e9)],
            max_usable_bandwidth_hz=20_000_000.0,
            max_sample_rate_hz=20_000_000.0,
        )
    ]


def _window() -> RfWindow:
    return RfWindow(
        id=uuid4(),
        window_key="w1",
        start_seconds=0.0,
        end_seconds=10.0,
        center_frequency_hz=2_450_000_000.0,
        bandwidth_hz=20_000_000.0,
        channels=[],
    )


async def test_full_lifecycle_over_a_real_nats_broker(nc: NATSClient, tmp_path: object) -> None:
    runtime = AgentRuntime(agent_id=AGENT_ID, capabilities=_capabilities(), cache_dir=tmp_path)  # type: ignore[arg-type]
    stop = asyncio.Event()
    task = asyncio.create_task(runtime.run(nc, stop))
    await asyncio.sleep(0.1)  # let the subscription establish

    async def agent_lookup(device_id: str) -> str | None:
        return AGENT_ID if device_id == DEVICE else None

    async def capabilities_lookup() -> list[PhysicalTxChannelCapability]:
        return _capabilities()

    adapter = RemoteAgentAdapter(nc, agent_lookup, capabilities_lookup)
    run_id = uuid4()

    try:
        lease = await adapter.reserve(DEVICE, CHANNEL, run_id, ttl_seconds=30.0)
        assert lease.device_id == DEVICE

        await adapter.preflight(DEVICE, CHANNEL, _window(), [])
        await adapter.configure(DEVICE, CHANNEL, _window())
        await adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
        await adapter.start(DEVICE, CHANNEL)

        status = await adapter.status(DEVICE, CHANNEL)
        assert status.transmitting is True

        await adapter.stop(DEVICE, CHANNEL)
        status = await adapter.status(DEVICE, CHANNEL)
        assert status.transmitting is False

        await adapter.emergency_stop(DEVICE, CHANNEL)
    finally:
        stop.set()
        await task
