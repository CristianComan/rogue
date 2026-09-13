"""Central lease enforcement (M8, ADR-008): renews every active run's
leases on a short interval, and emergency-stops a run whose lease has
lapsed without renewal, or whose renewal itself failed. This is the
*central* half of CLAUDE.md rule 12 ("safety is enforced centrally and
locally"); the Agent-side local watchdog (`agents/common/agent.py`) is the
independent local half, still enforcing even if this process is down.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rogue.domain.run import RunStatus
from rogue.execution.orchestrator import LEASE_TTL_SECONDS
from rogue.persistence import run as run_persistence

logger = logging.getLogger("rogue.execution.lease_sweep")

# Comfortably under LEASE_TTL_SECONDS so an active run gets several renewal
# attempts before its lease could actually lapse.
SWEEP_INTERVAL_SECONDS = LEASE_TTL_SECONDS / 3


async def sweep_once(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        active_runs = await run_persistence.list_active_runs(session)

    for scenario_id, run in active_runs:
        has_lapsed_lease = any(lease.expires_at <= datetime.now(UTC) for lease in run.device_leases)
        async with session_factory() as session:
            try:
                if has_lapsed_lease:
                    logger.warning(
                        "run %s has an expired, unrenewed lease; emergency-stopping", run.id
                    )
                    await run_persistence.emergency_stop_run(session, scenario_id, run.id)
                else:
                    renewed = await run_persistence.renew_run_leases(session, scenario_id, run.id)
                    if renewed.status == RunStatus.FAILED:
                        logger.warning(
                            "run %s failed to renew its leases; emergency-stopping", run.id
                        )
                        await run_persistence.emergency_stop_run(session, scenario_id, run.id)
                await session.commit()
            except Exception:
                logger.exception("lease sweep failed for run %s", run.id)
                await session.rollback()


async def run_lease_sweep_forever(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Runs until cancelled — intended to be wrapped in an `asyncio.Task`.

    A single tick failing (e.g. a transient DB error) must not end the
    background task for the rest of the process's lifetime — `sweep_once`
    already isolates per-run failures, this is the outer safety net.
    """
    while True:
        try:
            await sweep_once(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("lease sweep tick failed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
