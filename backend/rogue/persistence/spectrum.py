"""Spectrum-state persistence orchestration (M5).

Reuses ``repository.build_candidate_version`` (the same in-memory "what
would this draft publish as" logic ``validate_draft``/``publish_draft``
already use) and ``rogue.persistence.catalogue.get_recording`` (M4) to
resolve the recordings referenced by the candidate's emissions, then hands
both to the pure ``rogue.spectrum.occupancy.compute_spectrum_state``.

Lives in its own module rather than ``repository.py`` to avoid a circular
import: ``catalogue.py`` already imports from ``repository.py``, so
``repository.py`` cannot import ``catalogue.py`` back.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from rogue.domain.recording import IQRecording
from rogue.persistence import catalogue, repository
from rogue.spectrum.models import SpectrumState
from rogue.spectrum.occupancy import RecordingKey, compute_spectrum_state


async def spectrum_state_for_draft(
    session: AsyncSession, scenario_id: UUID, draft_id: UUID, at_seconds: float
) -> SpectrumState:
    """Compute the draft's deterministic spectrum state at ``at_seconds``.

    Raises ``repository.NotFoundError`` if the scenario/draft don't exist
    (propagated from ``build_candidate_version``).
    """
    candidate, _validation_findings = await repository.build_candidate_version(
        session, scenario_id, draft_id
    )

    recording_keys: set[RecordingKey] = {
        (emission.recording.recording_id, emission.recording.version)
        for mission in candidate.missions
        for link in mission.rf_links
        for emission in link.emissions
        if emission.recording is not None
    }
    recordings: dict[RecordingKey, IQRecording] = {}
    for recording_id, version in recording_keys:
        recording = await catalogue.get_recording(session, recording_id, version)
        if recording is not None:
            recordings[(recording_id, version)] = recording

    return compute_spectrum_state(candidate, at_seconds, recordings)
