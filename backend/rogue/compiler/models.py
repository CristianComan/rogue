"""Typed artifacts produced by the RF Environment Compiler (M6).

These are the compiler/scheduler artifacts ``rogue.domain.rf``'s module
docstring names but deliberately does not model — ``RfWindow``,
``CompositeChannel``, ``PhysicalTxChannel`` (here
``PhysicalTxChannelCapability`` + ``Allocation``), ``HardwareCapability``
and ``Allocation``. ``CompilerFinding`` mirrors
``rogue.domain.validation.ValidationFinding``'s shape and reuses its
``ValidationSeverity`` enum, matching ``rogue.spectrum.models.
SpectrumFinding``'s precedent.

``HardwareCapabilityProfile`` is a compile-time input, not runtime-
discovered hardware (CLAUDE.md rule 10 — that's M8/M10).
``DEFAULT_CAPABILITY_PROFILE`` below is an illustrative default matching
CLAUDE.md section 4's initial planning profile (2x X440 x 8ch, 2x AIR7311 x
4ch = 24 channels); see docs/decisions/ADR-006 for the exact numbers and
their rationale, including CLAUDE.md rule 4's restriction on native X440
paths in the 5.15-5.925 GHz band.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from rogue.domain.common import FrozenRogueModel
from rogue.domain.rf import FrequencyTransitionType, RfLinkRole
from rogue.domain.validation import ValidationSeverity


class RealizedFrequencyEvent(FrozenRogueModel):
    """A deterministically realized (link, time, frequency) transition.

    Unlike ``rogue.domain.rf.FrequencyEvent`` (authored worked-examples),
    this is the compiler's authoritative realized sequence for the compiled
    horizon (rf-model.md section 7).
    """

    link_id: UUID
    at_seconds: float
    frequency_hz: float
    transition_type: FrequencyTransitionType
    reason: str
    seed_context: int | None = None


class CompositeChannel(FrozenRogueModel):
    """One logical emission's contribution to an RfWindow at a point in time."""

    mission_id: UUID
    link_id: UUID
    role: RfLinkRole
    emission_id: UUID
    center_frequency_hz: float
    bandwidth_hz: float
    gain_offset_db: float


class RfWindow(FrozenRogueModel):
    """A contiguous wideband RF canvas (ADR-003), valid for [start, end) seconds.

    ``window_key`` identifies the same logical window across consecutive
    time spans (stable identity for allocation preference, rf-model.md
    section 8) — distinct from ``id``, which is unique per span.
    """

    id: UUID
    window_key: str
    start_seconds: float
    end_seconds: float
    center_frequency_hz: float
    bandwidth_hz: float
    channels: list[CompositeChannel]


class PhysicalTxChannelCapability(FrozenRogueModel):
    """One declared/simulated physical TX channel a plan may be allocated to."""

    device_id: str
    channel_index: int
    device_family: Literal["x440", "air7311", "simulated_generic"]
    tunable_ranges_hz: list[tuple[float, float]]
    max_usable_bandwidth_hz: float
    max_sample_rate_hz: float


class HardwareCapabilityProfile(FrozenRogueModel):
    """A named, swappable set of physical TX channel capabilities."""

    id: str
    channels: list[PhysicalTxChannelCapability]


class Allocation(FrozenRogueModel):
    """One RfWindow span's assignment to a physical TX channel."""

    window_key: str
    start_seconds: float
    end_seconds: float
    device_id: str
    channel_index: int
    is_migration: bool


class SafetyPolicyOutcome(FrozenRogueModel):
    """Structural default-deny placeholder (CLAUDE.md rule 12).

    The full lease/watchdog/emergency-stop policy engine is M8; a compiled
    Replay Plan alone never authorizes transmission.
    """

    tx_authorized: bool = False
    notes: str | None = (
        "TX authorization is granted at run preparation (M8), not at compile time"
    )


class CompilerFinding(FrozenRogueModel):
    """A single compiler-stage result, scoped to a JSON-pointer-like path."""

    severity: ValidationSeverity
    code: str
    message: str
    path: str


class RecordingManifestEntry(FrozenRogueModel):
    """One recording asset referenced by the plan, pinned by content hash."""

    recording_id: UUID
    version: int
    sha256_metadata: str
    sha256_data: str


class ReplayPlan(FrozenRogueModel):
    """Immutable, hardware-neutral executable plan compiled from a ScenarioVersion.

    "Hardware-neutral" per M6's exit criterion means bound to a declared/
    simulated ``capability_profile``, not runtime-discovered hardware (rule
    10) — see ADR-001 and ADR-006. Compiling the same
    (scenario_version, duration_s, capability_profile) is deterministic.
    """

    id: UUID
    scenario_id: UUID
    scenario_version_number: int
    compiler_version: str
    compiled_at: datetime
    duration_s: float
    capability_profile: HardwareCapabilityProfile
    recording_manifest: list[RecordingManifestEntry]
    realized_frequency_events: list[RealizedFrequencyEvent]
    rf_windows: list[RfWindow]
    allocations: list[Allocation]
    safety_policy_outcome: SafetyPolicyOutcome
    findings: list[CompilerFinding]


# X440's native RF path excludes 5.15-5.925 GHz (CLAUDE.md rule 4: that band
# requires an explicit modelled frequency-conversion chain, not modelled
# here); AIR7311 is the normal initial choice for that band instead.
X440_TUNABLE_RANGES_HZ: list[tuple[float, float]] = [(1e6, 5.15e9), (5.925e9, 6e9)]
AIR7311_TUNABLE_RANGES_HZ: list[tuple[float, float]] = [(70e6, 6e9)]

DEFAULT_CAPABILITY_PROFILE = HardwareCapabilityProfile(
    id="default-initial-planning-profile",
    channels=[
        PhysicalTxChannelCapability(
            device_id=f"x440-{unit}",
            channel_index=channel_index,
            device_family="x440",
            tunable_ranges_hz=X440_TUNABLE_RANGES_HZ,
            max_usable_bandwidth_hz=400e6,
            max_sample_rate_hz=500e6,
        )
        for unit in (1, 2)
        for channel_index in range(8)
    ]
    + [
        PhysicalTxChannelCapability(
            device_id=f"air7311-{unit}",
            channel_index=channel_index,
            device_family="air7311",
            tunable_ranges_hz=AIR7311_TUNABLE_RANGES_HZ,
            max_usable_bandwidth_hz=100e6,
            max_sample_rate_hz=125e6,
        )
        for unit in (1, 2)
        for channel_index in range(4)
    ],
)
