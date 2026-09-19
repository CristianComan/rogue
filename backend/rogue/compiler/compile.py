"""Top-level RF Environment Compiler entry point (M6).

Orchestrates realized-frequency-event generation
(``rogue.compiler.frequency``), RF window packing
(``rogue.compiler.windows``) and physical channel allocation
(``rogue.compiler.allocation``) into an immutable ``ReplayPlan``. Pure
function — no DB/I/O; callers (``rogue.persistence.replay``) resolve
recordings first, mirroring ``rogue.spectrum.occupancy``'s precedent.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from rogue.compiler.allocation import allocate_physical_channels
from rogue.compiler.frequency import realize_frequency_timeline
from rogue.compiler.models import (
    CompilerFinding,
    HardwareCapabilityProfile,
    RealizedFrequencyEvent,
    RecordingManifestEntry,
    ReplayPlan,
    SafetyPolicyOutcome,
)
from rogue.compiler.windows import compute_rf_windows
from rogue.domain.recording import IQRecording
from rogue.domain.rf import TimingSyncClass
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.occupancy import RecordingKey

COMPILER_VERSION = "0.1.0"

# Rank ordering for "strictest requested class wins" (M11, ADR-013) —
# TimingSyncClass has no inherent ordering as a StrEnum.
_SYNC_CLASS_RANK = {
    TimingSyncClass.L0_SIMULATED: 0,
    TimingSyncClass.L1_SOFTWARE_BARRIER: 1,
    TimingSyncClass.L2_SCHEDULED_LOCAL: 2,
    TimingSyncClass.L3_SHARED_REFERENCE: 3,
    TimingSyncClass.L4_MEASURED: 4,
}
# Neither vendor adapter exposes any PPS/PTP/timed-command capability today
# (agents/common/sdr_adapter_base.py) — L3/L4 genuinely can't be achieved,
# only declared. A scenario requesting one gets an honest warning rather
# than a silent claim of hardware capability that doesn't exist.
_UNACHIEVABLE_SYNC_CLASSES = {TimingSyncClass.L3_SHARED_REFERENCE, TimingSyncClass.L4_MEASURED}


def _required_sync_class(
    version: ScenarioVersion,
) -> tuple[TimingSyncClass, list[CompilerFinding]]:
    strictest = TimingSyncClass.L0_SIMULATED
    for mission in version.missions:
        for link in mission.rf_links:
            requested = (
                link.resource_preference.required_sync_class if link.resource_preference else None
            )
            if requested is not None and _SYNC_CLASS_RANK[requested] > _SYNC_CLASS_RANK[strictest]:
                strictest = requested

    if strictest not in _UNACHIEVABLE_SYNC_CLASSES:
        return strictest, []
    return strictest, [
        CompilerFinding(
            severity=ValidationSeverity.WARNING,
            code="sync_class_not_achievable",
            message=(
                f"scenario requests {strictest.value}, but no configured Agent capability "
                "supports shared PPS/PTP timing today — the best achievable class is "
                f"{TimingSyncClass.L1_SOFTWARE_BARRIER.value}"
            ),
            path="$",
        )
    ]


def compile_replay_plan(
    version: ScenarioVersion,
    recordings: Mapping[RecordingKey, IQRecording],
    duration_s: float,
    capability_profile: HardwareCapabilityProfile,
) -> ReplayPlan:
    """Compile ``version`` into a deterministic, hardware-neutral ReplayPlan.

    Findings (including any BLOCKING ones) are returned on the plan itself
    rather than raised — callers (``rogue.persistence.replay``) decide
    whether a BLOCKING finding means the plan should be persisted.
    """
    realized_events: list[RealizedFrequencyEvent] = [
        event
        for mission in version.missions
        for link in mission.rf_links
        for event in realize_frequency_timeline(link, duration_s)
    ]

    rf_windows, window_findings = compute_rf_windows(
        version, recordings, duration_s, capability_profile
    )
    allocations, allocation_findings = allocate_physical_channels(rf_windows, capability_profile)
    required_sync_class, sync_findings = _required_sync_class(version)

    manifest = [
        RecordingManifestEntry(
            recording_id=recording.id,
            version=recording.version,
            sha256_metadata=recording.sha256_metadata,
            sha256_data=recording.sha256_data,
        )
        for recording in sorted(recordings.values(), key=lambda r: (str(r.id), r.version))
    ]

    return ReplayPlan(
        id=uuid4(),
        scenario_id=version.scenario_id,
        scenario_version_number=version.version_number,
        compiler_version=COMPILER_VERSION,
        compiled_at=datetime.now(UTC),
        duration_s=duration_s,
        capability_profile=capability_profile,
        recording_manifest=manifest,
        realized_frequency_events=realized_events,
        rf_windows=rf_windows,
        allocations=allocations,
        safety_policy_outcome=SafetyPolicyOutcome(),
        findings=[*window_findings, *allocation_findings, *sync_findings],
        required_sync_class=required_sync_class,
    )
