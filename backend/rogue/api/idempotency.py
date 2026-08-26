"""Idempotency-Key handling for mutating scenario endpoints.

Per docs/architecture/system-design.md §7 ("Mutating requests use
idempotency keys") and CLAUDE.md's idempotency coding rule. A repeat
request with the same key and the same body replays the cached response
instead of re-executing; the same key with a *different* body is a
conflict (``repository.ConflictError``, mapped to 409 by
``rogue.api.errors``).

``replay_or_execute`` owns the transaction's single commit. ``execute``
must only stage writes (repository calls) and must NOT call
``session.commit()`` itself — the idempotency-key row has to be committed
in the *same* transaction as the business write it caches, or a second,
genuinely separate request (a new session, not just a re-used one) would
never see it and would silently re-execute instead of replaying.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from rogue.persistence import repository


async def replay_or_execute(
    session: AsyncSession,
    idempotency_key: str | None,
    endpoint: str,
    request_body_json: str,
    execute: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
) -> tuple[int, dict[str, Any]]:
    """Run ``execute()``, or replay a cached response for a repeated key."""
    if idempotency_key is None:
        status_code, body = await execute()
        await session.commit()
        return status_code, body

    request_hash = repository.hash_request_body(request_body_json.encode())
    cached = await repository.find_idempotent_response(
        session, idempotency_key, endpoint, request_hash
    )
    if cached is not None:
        return cached

    status_code, body = await execute()
    await repository.store_idempotent_response(
        session, idempotency_key, endpoint, request_hash, status_code, body
    )
    await session.commit()
    return status_code, body
