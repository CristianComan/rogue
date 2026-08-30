"""Typed results produced by rogue.spectrum.occupancy.

These are computed artifacts, not authored scenario intent, but they stay
frequency-domain-only (no physical device/channel data) — RF-window/hardware
allocation is M6, not modelled here. ``SpectrumFinding`` mirrors
``rogue.domain.validation.ValidationFinding``'s shape and reuses its
``ValidationSeverity`` enum rather than defining a parallel one.
"""

from __future__ import annotations

from uuid import UUID

from rogue.domain.common import FrozenRogueModel
from rogue.domain.rf import RfLinkRole
from rogue.domain.validation import ValidationSeverity


class FrequencyResolution(FrozenRogueModel):
    """The outcome of resolving a DroneRfLink's frequency at a scenario time."""

    link_id: UUID
    resolved: bool
    frequency_hz: float | None = None
    unresolved_reason: str | None = None


class OccupiedBand(FrozenRogueModel):
    """One RfEmission's occupied frequency range at a scenario time.

    ``headroom_hz`` is *spectral* headroom within the owning link's own
    declared ``RfBand`` (band width minus occupied bandwidth, floored at 0)
    — not RF power/clipping headroom, which requires RF-window/composite-
    channel modelling (M6) and isn't computed here.
    """

    mission_id: UUID
    link_id: UUID
    role: RfLinkRole
    emission_id: UUID
    center_frequency_hz: float
    bandwidth_hz: float
    freq_min_hz: float
    freq_max_hz: float
    headroom_hz: float


class SpectrumFinding(FrozenRogueModel):
    """A single spectrum-planning result, scoped to a JSON-pointer-like path."""

    severity: ValidationSeverity
    code: str
    message: str
    path: str


class SpectrumState(FrozenRogueModel):
    """Deterministic spectrum occupancy + conflict/headroom findings at one instant."""

    at_seconds: float
    occupied_bands: list[OccupiedBand]
    findings: list[SpectrumFinding]
