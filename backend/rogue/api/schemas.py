"""Thin request DTOs for the scenario API.

These omit server-assigned fields (id, timestamps, revision, ...) that the
full `rogue.domain` aggregates require; route handlers fill those in before
constructing a domain object. Responses reuse the domain models directly —
they're already Pydantic v2 and already the canonical shape.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rogue.domain.common import GeoPolygon
from rogue.domain.mission import DroneMission
from rogue.domain.receiver import Receiver
from rogue.domain.recording import AccessClassification, RecordingReference
from rogue.domain.scenario import Zone
from rogue.domain.timeline import TimelineEvent


class ScenarioCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    owner: str
    tags: list[str] = Field(default_factory=list)
    coordinate_system: str = "EPSG:4326"
    area_of_operation: GeoPolygon
    variables: dict[str, Any] = Field(default_factory=dict)


class DraftContent(BaseModel):
    """Content fields shared by draft-create and draft-update requests."""

    model_config = ConfigDict(extra="forbid")

    author: str
    zones: list[Zone] = Field(default_factory=list)
    missions: list[DroneMission] = Field(default_factory=list)
    receivers: list[Receiver] = Field(default_factory=list)
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    recordings: list[RecordingReference] = Field(default_factory=list)


class DraftCreateRequest(DraftContent):
    base_version_id: UUID | None = None


class DraftUpdateRequest(DraftContent):
    expected_revision: int = Field(ge=0)


class CloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    owner: str
    source_version_number: int | None = None


class CloneResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: UUID
    draft_id: UUID


class SpectrumStateRequest(BaseModel):
    """Scenario-time instant to compute deterministic spectrum state at."""

    model_config = ConfigDict(extra="forbid")

    at_seconds: float = Field(ge=0)


class RecordingIngestRequest(BaseModel):
    """Register a SigMF asset pair already uploaded to object storage.

    ``recording_id`` omitted registers a new catalogue entry; given, it adds
    a new version to that existing entry.
    """

    model_config = ConfigDict(extra="forbid")

    recording_id: UUID | None = None
    metadata_object_key: str
    data_object_key: str
    provenance: str | None = None
    access_classification: AccessClassification = AccessClassification.RESTRICTED
    allowed_use_constraints: list[str] = Field(default_factory=list)
    allowed_frequency_min_hz: float | None = None
    allowed_frequency_max_hz: float | None = None


class SpectrogramResponse(BaseModel):
    """A bounded time/frequency dB preview of a recording's I/Q content.

    Frequency bins are baseband-centered (0 Hz = the recording's own
    ``center_frequency_hz``, not any scenario RfLink's live authored
    frequency) — the caller re-centers for display.
    """

    model_config = ConfigDict(extra="forbid")

    time_offsets_s: list[float]
    freq_offsets_hz: list[float]
    magnitude_db: list[list[float]]
