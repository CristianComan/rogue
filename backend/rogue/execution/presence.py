"""Control-plane side of the shared presence subject (M8, ADR-008).

The M0 placeholder (`agents/common/main.py`) only ever published a
heartbeat; nothing in the control plane listened. This subscriber is what
turns that heartbeat into the queryable `GET /agents` inventory
(`rogue.persistence.agents`).
"""

from __future__ import annotations

import logging

from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg

from rogue.db.session import async_session_factory
from rogue.persistence import agents as agents_persistence
from rogue.protocol.messages import AgentPresence
from rogue.protocol.subjects import PRESENCE_SUBJECT

logger = logging.getLogger("rogue.execution.presence")


async def _handle(msg: Msg) -> None:
    presence = AgentPresence.model_validate_json(msg.data)
    async with async_session_factory() as session:
        await agents_persistence.record_presence(session, presence)
        await session.commit()


async def subscribe_presence_forever(nc: NATSClient) -> None:
    """Runs until cancelled — intended to be wrapped in an `asyncio.Task`."""
    subscription = await nc.subscribe(PRESENCE_SUBJECT)
    async for msg in subscription.messages:
        try:
            await _handle(msg)
        except Exception:
            logger.exception("failed to process a presence heartbeat")
