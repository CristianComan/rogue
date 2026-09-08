"""HTTP-level tests for the Agent inventory API (M8)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from rogue.persistence import agents as agents_persistence
from rogue.protocol.messages import AgentPresence


async def _seed_agent(connection: AsyncConnection, agent_id: str) -> None:
    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with session_factory() as session:
        await agents_persistence.record_presence(
            session, AgentPresence(agent_id=agent_id, mode="simulated", seen_at=datetime.now(UTC))
        )
        await session.commit()


async def test_list_agents_returns_seeded_presence(
    client: TestClient, connection: AsyncConnection
) -> None:
    await _seed_agent(connection, "sim-agent-01")

    response = client.get("/agents")

    assert response.status_code == 200
    body = response.json()
    assert [a["agent_id"] for a in body] == ["sim-agent-01"]
    assert body[0]["status"] == "online"


async def test_get_agent_returns_404_for_unknown_agent(client: TestClient) -> None:
    response = client.get("/agents/does-not-exist")

    assert response.status_code == 404


async def test_get_agent_returns_the_agent(client: TestClient, connection: AsyncConnection) -> None:
    await _seed_agent(connection, "sim-agent-02")

    response = client.get("/agents/sim-agent-02")

    assert response.status_code == 200
    assert response.json()["agent_id"] == "sim-agent-02"
