"""FastAPI TestClient fixture backed by a real Postgres/PostGIS transaction.

Each *request* gets its own ``AsyncSession`` — a fresh
``session_factory()`` call per ``get_session`` dependency resolution, same
as production — bound to one shared connection/transaction via
``join_transaction_mode="create_savepoint"`` so the whole test still rolls
back at the end. This matters: a fixture that reuses one session object
across every request in a test hides bugs where a handler's writes were
never actually committed, since the second call would see the first call's
*uncommitted* work anyway. That masked exactly this bug in the
Idempotency-Key handling — see the M2 completion notes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from rogue.db.session import engine, get_session
from rogue.main import app


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()


@pytest.fixture
def client(connection: AsyncConnection) -> Iterator[TestClient]:
    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async def override_get_session() -> AsyncIterator[object]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
