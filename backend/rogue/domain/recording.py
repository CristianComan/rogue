"""SigMF recording references used by scenario RF emissions.

Full catalogue ingest/parsing is M4 (SigMF catalogue). This module defines
the typed reference/asset-metadata shape that scenarios use to point at a
recording, per docs/architecture/domain-model.md's IQRecording entity.
Unknown SigMF extension namespaces are preserved rather than dropped, per
CLAUDE.md non-negotiable architecture rule 7.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from rogue.domain.common import IdentifiedMixin, RogueModel


class AccessClassification(StrEnum):
    """Handling/dissemination classification for a recording asset."""

    PUBLIC = "public"
    RESTRICTED = "restricted"
    CONTROLLED = "controlled"


class RecordingKind(StrEnum):
    """Whether a recording is a signal of interest or an ambient/noise-floor capture.

    Set at ingest, not re-decided per emission — an RfEmission that wants to
    play "background only" for a span picks a RecordingKind.BACKGROUND
    recording via the same RecordingReference mechanism as any other.
    """

    SIGNAL = "signal"
    BACKGROUND = "background"


class RecordingReference(RogueModel):
    """Lightweight pointer to a specific, versioned IQRecording."""

    recording_id: UUID
    version: int = Field(ge=1)
    note: str | None = None


class SpectrogramOverview(RogueModel):
    """A coarse, whole-recording time/frequency dB preview, computed once at ingest.

    Sparsely sampled (a small, fixed number of short FFT windows spread
    across the recording), not a continuous STFT of every sample — a full
    live STFT over a real recording's sample rate is prohibitively large to
    compute per request (see catalogue/spectrogram.py's module docstring for
    the measurement that drove this). Good enough for a scrubbing preview;
    not a compiled/conflict-checked plan.
    """

    time_offsets_s: list[float]
    freq_offsets_hz: list[float]
    magnitude_db: list[list[float]]


class IQRecording(IdentifiedMixin):
    """Immutable SigMF asset/version reference.

    ``extra_sigmf_fields`` retains unknown SigMF extension namespace keys
    verbatim so ingest never silently discards metadata the platform does
    not yet interpret.
    """

    version: int = Field(ge=1)
    metadata_object_key: str
    data_object_key: str
    sha256_metadata: str
    sha256_data: str
    sample_format: str
    sample_rate_hz: float = Field(gt=0)
    sample_count: int = Field(ge=0)
    duration_s: float = Field(ge=0)
    center_frequency_hz: float | None = None
    kind: RecordingKind = RecordingKind.SIGNAL
    overview_spectrogram: SpectrogramOverview | None = None
    provenance: str | None = None
    access_classification: AccessClassification = AccessClassification.RESTRICTED
    allowed_use_constraints: list[str] = Field(default_factory=list)
    allowed_frequency_min_hz: float | None = None
    allowed_frequency_max_hz: float | None = None
    extra_sigmf_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256_metadata", "sha256_data")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value):
            raise ValueError("must be a 64-character hex SHA-256 digest")
        return value.lower()

    def reference(self) -> RecordingReference:
        """Build the lightweight reference other entities embed."""
        return RecordingReference(recording_id=self.id, version=self.version)
