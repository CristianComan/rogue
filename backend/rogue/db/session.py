"""Async SQLAlchemy engine/session wiring.

FastAPI route handlers depend on ``get_session`` to receive a request-scoped
``AsyncSession``; nothing outside this module should construct the engine or
sessionmaker directly, so tests can override the dependency cleanly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rogue.settings import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session; the caller controls commit/rollback."""
    async with async_session_factory() as session:
        yield session
