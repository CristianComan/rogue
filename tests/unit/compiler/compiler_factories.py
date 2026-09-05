"""Minimal, valid object builders for compiler (M6) tests.

Deliberately not shared with tests/unit/spectrum/spectrum_factories.py:
pytest's rootdir-based import (no __init__.py in either directory) makes
each test directory its own top-level import namespace, so cross-directory
imports aren't reliable when a test subset runs in isolation — same
rationale as spectrum_factories.py's own docstring.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from rogue.compiler.models import (
    HardwareCapabilityProfile,
    PhysicalTxChannelCapability,
)
from rogue.domain.common import GeoPoint, GeoPolygon
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


def area_polygon() -> GeoPolygon:
    ring = [(13.0, 52.0), (13.5, 52.0), (13.5, 52.5), (13.0, 52.5), (13.0, 52.0)]
    return GeoPolygon(coordinates=[ring])


def make_recording(**overrides: Any) -> IQRecording:
    kwargs: dict[str, Any] = {
        "version": 1,
        "metadata_object_key": "recordings/demo/v1.sigmf-meta",
        "data_object_key": "recordings/demo/v1.sigmf-data",
        "sha256_metadata": VALID_SHA256,
        "sha256_data": VALID_SHA256,
        "sample_format": "cf32_le",
        "sample_rate_hz": 1_000_000.0,
        "sample_count": 1_000_000,
        "duration_s": 1.0,
        "access_classification": AccessClassification.RESTRICTED,
    }
    kwargs.update(overrides)
    return IQRecording(**kwargs)


def make_link(
    recording_ref: RecordingReference,
    *,
    mode: FrequencySwitchingMode = FrequencySwitchingMode.SCRIPTED,
    band: RfBand | None = None,
    emissions: list[RfEmission] | None = None,
    **behaviour_overrides: Any,
) -> DroneRfLink:
    behaviour_kwargs: dict[str, Any] = {"mode": mode}
    if mode == FrequencySwitchingMode.SCRIPTED:
        behaviour_kwargs["scripted_changes"] = behaviour_overrides.pop(
            "scripted_changes",
            [ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_412_000_000.0)],
        )
    elif mode == FrequencySwitchingMode.MISSION_TRIGGERED:
        behaviour_kwargs["mission_trigger_anchor"] = behaviour_overrides.pop(
            "mission_trigger_anchor", "waypoint:1"
        )
    elif mode == FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE:
        behaviour_kwargs["random_seed"] = behaviour_overrides.pop("random_seed", 42)
        behaviour_kwargs["mean_dwell_s"] = behaviour_overrides.pop("mean_dwell_s", 5.0)
    elif mode == FrequencySwitchingMode.EXTERNAL_STATE_TRIGGERED:
        behaviour_kwargs["external_trigger_reference"] = behaviour_overrides.pop(
            "external_trigger_reference", "geofence-breach"
        )
    behaviour_kwargs.update(behaviour_overrides)

    return DroneRfLink(
        role=RfLinkRole.C2,
        band=band or RfBand(freq_min_hz=2_400_000_000.0, freq_max_hz=2_483_500_000.0),
        frequency_behaviour=FrequencyBehaviour(**behaviour_kwargs),
        emissions=emissions or [RfEmission(recording=recording_ref, start_offset=timedelta(0))],
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
    """A small two-channel profile, cheap to reason about in tests."""
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
