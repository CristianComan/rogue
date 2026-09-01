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

from rogue.compiler.models import HardwareCapabilityProfile
from rogue.domain.common import GeoPolygon
from rogue.domain.mission import DroneMission
from rogue.domain.receiver import Receiver
from rogue.domain.recording import AccessClassification, RecordingKind
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
    """Content fields shared by draft-create and draft-update requests.

    No ``recordings`` field: it's never client-authored — the server always
    derives it from ``missions[].rf_links[].emissions[]`` via
    ``rogue.domain.scenario.derive_recording_references``. A request body
    still including a ``recordings`` key gets a 422 from ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")

    author: str
    zones: list[Zone] = Field(default_factory=list)
    missions: list[DroneMission] = Field(default_factory=list)
    receivers: list[Receiver] = Field(default_factory=list)
    timeline_events: list[TimelineEvent] = Field(default_factory=list)


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


class CompileRequest(BaseModel):
    """Compile-time inputs for the RF Environment Compiler (M6).

    ``capability_profile`` omitted uses ``rogue.compiler.models.
    DEFAULT_CAPABILITY_PROFILE`` (the illustrative 24-channel initial
    planning profile from CLAUDE.md section 4) rather than runtime-
    discovered hardware — that's M8/M10, per CLAUDE.md rule 10.
    """

    model_config = ConfigDict(extra="forbid")

    duration_s: float = Field(gt=0)
    capability_profile: HardwareCapabilityProfile | None = None


class RunCreateRequest(BaseModel):
    """Who is executing a compiled ReplayPlan (M7)."""

    model_config = ConfigDict(extra="forbid")

    operator: str


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
    kind: RecordingKind = RecordingKind.SIGNAL
    access_classification: AccessClassification = AccessClassification.RESTRICTED
    allowed_use_constraints: list[str] = Field(default_factory=list)
    allowed_frequency_min_hz: float | None = None
    allowed_frequency_max_hz: float | None = None
