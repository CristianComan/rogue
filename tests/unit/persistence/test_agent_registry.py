"""Tests for the presence-driven agent registry (M8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from rogue.compiler.models import PhysicalTxChannelCapability
from rogue.domain.agent import PRESENCE_STALE_AFTER_SECONDS
from rogue.persistence import agents as agents_persistence
from rogue.protocol.messages import AgentPresence


def make_capability(device_id: str, channel_index: int) -> PhysicalTxChannelCapability:
    return PhysicalTxChannelCapability(
        device_id=device_id,
        channel_index=channel_index,
        device_family="simulated_generic",
        tunable_ranges_hz=[(1e6, 6e9)],
        max_usable_bandwidth_hz=20_000_000.0,
        max_sample_rate_hz=20_000_000.0,
    )


async def test_record_presence_then_list_returns_it(session: AsyncSession) -> None:
    presence = AgentPresence(
        agent_id="sim-agent-01",
        mode="simulated",
        capabilities=[make_capability("sim-1", 0)],
        seen_at=datetime.now(UTC),
    )

    await agents_persistence.record_presence(session, presence)
    agents = await agents_persistence.list_agents(session)

    assert [a.agent_id for a in agents] == ["sim-agent-01"]
    assert agents[0].status == "online"


async def test_record_presence_upserts_the_same_agent(session: AsyncSession) -> None:
    await agents_persistence.record_presence(
        session,
        AgentPresence(agent_id="sim-agent-01", mode="simulated", seen_at=datetime.now(UTC)),
    )
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="sim-agent-01",
            mode="simulated",
            capabilities=[make_capability("sim-1", 0)],
            seen_at=datetime.now(UTC),
        ),
    )

    agents = await agents_persistence.list_agents(session)

    assert len(agents) == 1
    assert len(agents[0].capabilities) == 1


async def test_get_agent_for_device_finds_the_owning_agent(session: AsyncSession) -> None:
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="sim-agent-01",
            mode="simulated",
            capabilities=[make_capability("sim-1", 0)],
            seen_at=datetime.now(UTC),
        ),
    )
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="sim-agent-02",
            mode="simulated",
            capabilities=[make_capability("sim-2", 0)],
            seen_at=datetime.now(UTC),
        ),
    )

    assert await agents_persistence.get_agent_for_device(session, "sim-2") == "sim-agent-02"
    assert await agents_persistence.get_agent_for_device(session, "unknown") is None


async def test_get_agent_returns_none_for_unknown_agent(session: AsyncSession) -> None:
    assert await agents_persistence.get_agent(session, "does-not-exist") is None


# --- aggregate_capability_profile (M10, ADR-010) ---


async def test_aggregate_capability_profile_returns_none_with_no_agents(
    session: AsyncSession,
) -> None:
    assert await agents_persistence.aggregate_capability_profile(session) is None


async def test_aggregate_capability_profile_returns_none_when_all_agents_are_stale(
    session: AsyncSession,
) -> None:
    stale_at = datetime.now(UTC) - timedelta(seconds=PRESENCE_STALE_AFTER_SECONDS + 5)
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="sim-agent-01",
            mode="simulated",
            capabilities=[make_capability("sim-1", 0)],
            seen_at=stale_at,
        ),
    )

    assert await agents_persistence.aggregate_capability_profile(session) is None


async def test_aggregate_capability_profile_spans_online_agents_of_both_families(
    session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="x440-agent",
            mode="x440",
            capabilities=[make_capability("x440-1", 0), make_capability("x440-1", 1)],
            seen_at=now,
        ),
    )
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="air7311-agent",
            mode="air7311",
            capabilities=[make_capability("air7311-1", 0)],
            seen_at=now,
        ),
    )

    profile = await agents_persistence.aggregate_capability_profile(session)

    assert profile is not None
    device_ids = {c.device_id for c in profile.channels}
    assert device_ids == {"x440-1", "air7311-1"}
    assert len(profile.channels) == 3


async def test_aggregate_capability_profile_excludes_a_stale_agents_capabilities(
    session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    stale_at = now - timedelta(seconds=PRESENCE_STALE_AFTER_SECONDS + 5)
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="online-agent",
            mode="x440",
            capabilities=[make_capability("x440-1", 0)],
            seen_at=now,
        ),
    )
    await agents_persistence.record_presence(
        session,
        AgentPresence(
            agent_id="stale-agent",
            mode="air7311",
            capabilities=[make_capability("air7311-1", 0)],
            seen_at=stale_at,
        ),
    )

    profile = await agents_persistence.aggregate_capability_profile(session)

    assert profile is not None
    assert {c.device_id for c in profile.channels} == {"x440-1"}
