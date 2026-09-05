"""Minimal, valid object builders for execution (M7) tests.

Deliberately not shared with tests/unit/compiler/compiler_factories.py:
pytest's rootdir-based import (no __init__.py in either directory) makes
each test directory its own top-level import namespace, so cross-directory
imports aren't reliable when a test subset runs in isolation — same
rationale as compiler_factories.py's own docstring.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from rogue.compiler.compile import compile_replay_plan
from rogue.compiler.models import (
    HardwareCapabilityProfile,
    PhysicalTxChannelCapability,
    ReplayPlan,
)
from rogue.domain.common import GeoPoint
from rogue.domain.mission import (
    AltitudeReference,
    DroneMission,
    MissionTemplate,
    Platform,
    PlatformCategory,
    Trajectory,
    Waypoint,
)
from rogue.domain.recording import AccessClassification, IQRecording, RecordingReference
from rogue.domain.rf import (
    DroneRfLink,
    FrequencyBehaviour,
    FrequencySwitchingMode,
    RfBand,
    RfEmission,
    RfLinkRole,
    ScriptedFrequencyChange,
)
from rogue.domain.scenario import ScenarioVersion

VALID_SHA256 = "a" * 64


def make_recording(**overrides: Any) -> IQRecording:
    kwargs: dict[str, Any] = {
        "version": 1,
        "metadata_object_key": "recordings/demo/v1.sigmf-meta",
        "data_object_key": "recordings/demo/v1.sigmf-data",
        "sha256_metadata": VALID_SHA256,
        "sha256_data": VALID_SHA256,
        "sample_format": "cf32_le",
        "sample_rate_hz": 1_000_000.0,
        "sample_count": 100_000_000,
        "duration_s": 100.0,
        "access_classification": AccessClassification.RESTRICTED,
    }
    kwargs.update(overrides)
    return IQRecording(**kwargs)


def make_link(
    recording_ref: RecordingReference,
    *,
    band: RfBand | None = None,
    frequency_hz: float = 2_412_000_000.0,
) -> DroneRfLink:
    return DroneRfLink(
        role=RfLinkRole.C2,
        band=band or RfBand(freq_min_hz=2_400_000_000.0, freq_max_hz=2_483_500_000.0),
        frequency_behaviour=FrequencyBehaviour(
            mode=FrequencySwitchingMode.SCRIPTED,
            scripted_changes=[
                ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=frequency_hz)
            ],
        ),
        emissions=[RfEmission(recording=recording_ref, start_offset=timedelta(0))],
    )


def make_mission(rf_links: list[DroneRfLink]) -> DroneMission:
    return DroneMission(
        name="recon-1",
        platform=Platform(
            name="Generic Quad", category=PlatformCategory.MULTIROTOR, max_speed_mps=18.0
        ),
        trajectory=Trajectory(
            template=MissionTemplate.WAYPOINT_TRANSIT,
            waypoints=[
                Waypoint(
                    sequence_index=0,
                    position=GeoPoint(coordinates=(13.40, 52.20)),
                    altitude_m=100.0,
                    altitude_reference=AltitudeReference.AGL,
                ),
                Waypoint(
                    sequence_index=1,
                    position=GeoPoint(coordinates=(13.45, 52.25)),
                    altitude_m=100.0,
                    altitude_reference=AltitudeReference.AGL,
                ),
            ],
            default_speed_mps=12.0,
        ),
        rf_links=rf_links,
    )


def make_scenario_version(
    missions: list[DroneMission], recordings: list[RecordingReference]
) -> ScenarioVersion:
    return ScenarioVersion(
        id=uuid4(),
        scenario_id=uuid4(),
        version_number=1,
        missions=missions,
        recordings=recordings,
        author="test-operator",
    )


def recording_key(ref: RecordingReference) -> tuple[UUID, int]:
    return (ref.recording_id, ref.version)


def make_capability_profile(**overrides: Any) -> HardwareCapabilityProfile:
    kwargs: dict[str, Any] = {
        "id": "test-profile",
        "channels": [
            PhysicalTxChannelCapability(
                device_id="sim-1",
                channel_index=0,
                device_family="simulated_generic",
                tunable_ranges_hz=[(1e6, 6e9)],
                max_usable_bandwidth_hz=20_000_000.0,
                max_sample_rate_hz=20_000_000.0,
            ),
            PhysicalTxChannelCapability(
                device_id="sim-1",
                channel_index=1,
                device_family="simulated_generic",
                tunable_ranges_hz=[(1e6, 6e9)],
                max_usable_bandwidth_hz=20_000_000.0,
                max_sample_rate_hz=20_000_000.0,
            ),
        ],
    }
    kwargs.update(overrides)
    return HardwareCapabilityProfile(**kwargs)


def make_plan_and_recordings(
    duration_s: float = 20.0,
) -> tuple[ReplayPlan, dict[tuple[UUID, int], IQRecording]]:
    """A single-link, single-window, single-allocation happy-path plan."""
    recording = make_recording()
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    plan = compile_replay_plan(
        version, recordings, duration_s=duration_s, capability_profile=profile
    )
    assert plan.allocations, "expected the happy-path fixture to compile at least one allocation"
    return plan, recordings


def make_plan_and_recordings_two_channels(
    duration_s: float = 20.0,
) -> tuple[ReplayPlan, dict[tuple[UUID, int], IQRecording]]:
    """Two links far enough apart in frequency to pack into two separate
    windows/physical channels, each with its own distinct recording — for
    asserting a channel's PREFLIGHT only receives *its own* recording(s),
    not the whole plan's manifest (M9, ADR-009).
    """
    recording_a = make_recording(metadata_object_key="recordings/a/v1.sigmf-meta")
    recording_b = make_recording(metadata_object_key="recordings/b/v1.sigmf-meta")
    link_a = make_link(recording_a.reference(), frequency_hz=2_412_000_000.0)
    link_b = make_link(
        recording_b.reference(),
        band=RfBand(freq_min_hz=5.15e9, freq_max_hz=5.25e9),
        frequency_hz=5_200_000_000.0,
    )
    version = make_scenario_version(
        [make_mission([link_a, link_b])],
        [recording_a.reference(), recording_b.reference()],
    )
    recordings = {
        recording_key(recording_a.reference()): recording_a,
        recording_key(recording_b.reference()): recording_b,
    }
    profile = make_capability_profile()

    plan = compile_replay_plan(
        version, recordings, duration_s=duration_s, capability_profile=profile
    )
    assert len(plan.allocations) == 2, "expected each link to land on its own physical channel"
    return plan, recordings
