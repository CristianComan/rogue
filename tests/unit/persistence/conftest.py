"""Shared fixtures for persistence tests.

Each test runs inside one outer database transaction that is rolled back
afterwards, so tests never commit and never depend on execution order or a
shared, growing dataset. Requires a running Postgres/PostGIS — see
``docker compose up -d postgres`` — matching CLAUDE.md's rule against
swapping in a different database for tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rogue.db.session import engine


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with session_factory() as db_session:
            yield db_session
        await transaction.rollback()
