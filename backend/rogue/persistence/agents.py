"""Agent inventory persistence (M8) — upserts driven by presence heartbeats.

Mirrors ``rogue.persistence.run``'s mutable-JSONB-document shape. ``status``
(``SDRAgentRecord.status``) is a computed field derived from ``last_seen_at``
at read time, so it is deliberately excluded from the stored document —
storing it would let a stale value linger in the database independent of
whether a heartbeat has actually arrived since (CLAUDE.md rule 10: runtime
discovery is authoritative, not a cached derivation of it).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.compiler.models import HardwareCapabilityProfile
from rogue.db.models import SDRAgentORM
from rogue.domain.agent import AgentStatus, SDRAgentRecord
from rogue.protocol.messages import AgentPresence


def _orm_to_record(row: SDRAgentORM) -> SDRAgentRecord:
    return SDRAgentRecord.model_validate(row.document)


async def record_presence(session: AsyncSession, presence: AgentPresence) -> SDRAgentRecord:
    """Upsert the calling agent's latest heartbeat."""
    record = SDRAgentRecord(
        agent_id=presence.agent_id,
        mode=presence.mode,
        capabilities=presence.capabilities,
        last_seen_at=presence.seen_at,
    )
    document = record.model_dump(mode="json", exclude={"status"})

    row = await session.get(SDRAgentORM, presence.agent_id)
    if row is None:
        session.add(
            SDRAgentORM(agent_id=presence.agent_id, document=document, updated_at=presence.seen_at)
        )
    else:
        row.document = document
        row.updated_at = presence.seen_at
    await session.flush()
    return record


async def list_agents(session: AsyncSession) -> list[SDRAgentRecord]:
    result = await session.execute(select(SDRAgentORM).order_by(SDRAgentORM.agent_id))
    return [_orm_to_record(row) for row in result.scalars()]


async def get_agent(session: AsyncSession, agent_id: str) -> SDRAgentRecord | None:
    row = await session.get(SDRAgentORM, agent_id)
    return _orm_to_record(row) if row is not None else None


async def get_agent_for_device(session: AsyncSession, device_id: str) -> str | None:
    """The agent_id currently reporting `device_id` among its capabilities.

    Used by `RemoteAgentAdapter` to route a command to the right per-agent
    NATS subject (ADR-008). Returns the first match; capability_profile
    device_id ownership is not expected to overlap between agents.
    """
    for record in await list_agents(session):
        if any(channel.device_id == device_id for channel in record.capabilities):
            return record.agent_id
    return None


async def aggregate_capability_profile(session: AsyncSession) -> HardwareCapabilityProfile | None:
    """A `HardwareCapabilityProfile` built from every currently-`online`
    registered agent's reported capabilities, spanning both hardware
    families (the registry doesn't distinguish by family — an X440 agent
    and an AIR7311 agent both just contribute `PhysicalTxChannelCapability`
    entries) — the "runtime discovery is authoritative" half of CLAUDE.md
    rule 10 (M10, ADR-010).

    Returns `None` if no agent is currently online, so the caller's static-
    default fallback stays an explicit decision rather than this silently
    returning an empty profile that would reject every compile.
    """
    channels = [
        channel
        for record in await list_agents(session)
        if record.status == AgentStatus.ONLINE
        for channel in record.capabilities
    ]
    if not channels:
        return None
    return HardwareCapabilityProfile(id="live-agent-registry", channels=channels)
