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
from rogue.domain.recording import RecordingReference
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

    ``recording`` carries the active emission's ``RecordingReference``
    through to M6's ``CompositeChannel`` (M9, ADR-009) — this is what lets a
    real adapter know which cached SigMF asset to actually stream for a
    given physical channel; it was dropped on the floor before M9 needed it
    for anything.
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
    recording: RecordingReference

    # The owning link's DroneRfLink.observed_by_receiver_id (region/receiver
    # simulation semantics, ADR-015) — a straight passthrough, unlike the
    # coherent-group fields below: it's already fully resolved on the link
    # itself, no expansion/geometry step needed. Carried through to M6's
    # CompositeChannel the same way `recording` is, for a future planning
    # sync matrix / run channel display.
    observed_by_receiver_id: UUID | None = None

    # Coherent-group fields (ADR-012): always None as produced by
    # compute_spectrum_state below — M5 has no receiver-geometry awareness.
    # Populated only by rogue.compiler.windows's coherent-group expansion
    # step (M6), one band per target Receiver array element, before
    # _pack_bands runs — same "M6-forward-looking field on an M5 model"
    # precedent as this class's own `recording` field (see its docstring).
    coherent_group_id: UUID | None = None
    array_element_receiver_id: UUID | None = None
    phase_offset_rad: float | None = None
    delay_offset_s: float | None = None


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
