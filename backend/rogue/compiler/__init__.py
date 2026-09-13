"""RF Environment Compiler (M6): compiles a published ScenarioVersion into
an immutable, hardware-neutral ReplayPlan. See docs/architecture/
rf-model.md and docs/decisions/ADR-001, ADR-003, ADR-006.
"""

from __future__ import annotations

from rogue.compiler.compile import COMPILER_VERSION, compile_replay_plan
from rogue.compiler.models import (
    DEFAULT_CAPABILITY_PROFILE,
    Allocation,
    CompilerFinding,
    CompositeChannel,
    HardwareCapabilityProfile,
    PhysicalTxChannelCapability,
    RealizedFrequencyEvent,
    RecordingManifestEntry,
    ReplayPlan,
    RfWindow,
    SafetyPolicyOutcome,
)

__all__ = [
    "COMPILER_VERSION",
    "DEFAULT_CAPABILITY_PROFILE",
    "Allocation",
    "CompilerFinding",
    "CompositeChannel",
    "HardwareCapabilityProfile",
    "PhysicalTxChannelCapability",
    "RealizedFrequencyEvent",
    "RecordingManifestEntry",
    "ReplayPlan",
    "RfWindow",
    "SafetyPolicyOutcome",
    "compile_replay_plan",
]
