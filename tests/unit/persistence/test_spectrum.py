"""Spectrum persistence tests against a real Postgres (see conftest.py).

Inserts an IQRecordingORM row directly rather than going through
``catalogue.ingest_recording`` (which needs object-storage data) — these
tests only need a resolvable recording for bandwidth lookup, not a full
ingest round-trip (that's covered by test_catalogue.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from persistence_factories import make_draft, make_mission, make_recording, make_scenario
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.db.models import IQRecordingORM
from rogue.persistence import repository, spectrum


async def test_spectrum_state_for_draft_computes_occupied_band(session: AsyncSession) -> None:
    scenario = await repository.create_scenario(session, make_scenario())
    recording = make_recording()
    session.add(
        IQRecordingORM(
            id=recording.id,
            version=recording.version,
            document=recording.model_dump(mode="json"),
            access_classification=recording.access_classification.value,
            provenance=None,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()

    ref = recording.reference()
    draft = make_draft(scenario.id, missions=[make_mission(ref)], recordings=[ref])
    await repository.create_draft(session, draft)

    state = await spectrum.spectrum_state_for_draft(session, scenario.id, draft.id, at_seconds=0.0)

    assert len(state.occupied_bands) == 1
    assert state.occupied_bands[0].bandwidth_hz == recording.sample_rate_hz
    assert state.findings == []


async def test_spectrum_state_for_draft_missing_recording_is_a_warning(
    session: AsyncSession,
) -> None:
    scenario = await repository.create_scenario(session, make_scenario())
    ref = make_recording().reference()  # never persisted
    draft = make_draft(scenario.id, missions=[make_mission(ref)], recordings=[ref])
    await repository.create_draft(session, draft)

    state = await spectrum.spectrum_state_for_draft(session, scenario.id, draft.id, at_seconds=0.0)

    assert state.occupied_bands == []
    assert any(f.code == "recording_unavailable" for f in state.findings)


async def test_spectrum_state_for_draft_missing_draft_raises_not_found(
    session: AsyncSession,
) -> None:
    scenario = await repository.create_scenario(session, make_scenario())

    with pytest.raises(repository.NotFoundError):
        await spectrum.spectrum_state_for_draft(session, scenario.id, uuid4(), at_seconds=0.0)
