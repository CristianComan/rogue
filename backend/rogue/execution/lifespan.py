"""FastAPI lifespan (M8): connects to NATS and starts the background
presence subscriber + lease-sweep task alongside the API process. Neither
existed before M8 — nothing previously listened for presence, and there was
no lease to sweep (ADR-007's `DeviceLease` had no expiry).

A NATS connection failure at startup is logged and degrades gracefully
(the agent registry stays empty, dispatch stays whatever
``settings.agent_dispatch_mode`` already defaults to) rather than crashing
the API — docker-compose's own ``depends_on: nats: condition:
service_healthy`` is what actually guarantees NATS is reachable in that
environment; this fallback only matters for ad hoc local runs without
compose.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import nats
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from rogue.db.session import engine
from rogue.execution import lease_sweep, presence
from rogue.persistence import run as run_persistence
from rogue.settings import settings

logger = logging.getLogger("rogue.execution.lifespan")

_CONNECT_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    tasks: list[asyncio.Task[None]] = []
    nc = None
    try:
        nc = await nats.connect(settings.nats_url, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    except Exception:
        logger.warning(
            "could not connect to NATS at %s; agent registry/lease-sweep disabled",
            settings.nats_url,
        )

    if nc is not None:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        tasks.append(asyncio.create_task(presence.subscribe_presence_forever(nc)))
        tasks.append(asyncio.create_task(lease_sweep.run_lease_sweep_forever(session_factory)))
        if settings.agent_dispatch_mode == "distributed":
            run_persistence.configure_distributed_dispatch(nc, session_factory)

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if nc is not None:
            await nc.drain()
