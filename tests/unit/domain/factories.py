"""Minimal, valid domain object builders shared across domain model tests.

Each ``*_kwargs`` function returns a plain dict of constructor arguments so
tests can override individual fields to exercise validation failures
without repeating the whole object graph.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from rogue.domain.common import GeoPoint, GeoPolygon
from rogue.domain.mission import (
    AltitudeReference,
    DroneMission,
    MissionStartPolicy,
    MissionTemplate,
    Platform,
    PlatformCategory,
    Trajectory,
    Waypoint,
)
from rogue.domain.receiver import Receiver, ReceiverType
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
from rogue.domain.scenario import Scenario, ScenarioVersion, Zone, ZoneType
from rogue.domain.timeline import AbsoluteTimelineEvent

VALID_SHA256 = "a" * 64


def geo_point(lon: float = 13.404954, lat: float = 52.520008, alt: float | None = None) -> GeoPoint:
    coordinates = (lon, lat) if alt is None else (lon, lat, alt)
    return GeoPoint(coordinates=coordinates)


def area_polygon() -> GeoPolygon:
    ring = [(13.0, 52.0), (13.5, 52.0), (13.5, 52.5), (13.0, 52.5), (13.0, 52.0)]
    return GeoPolygon(coordinates=[ring])


def iq_recording_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "version": 1,
        "metadata_object_key": "recordings/demo/v1.sigmf-meta",
        "data_object_key": "recordings/demo/v1.sigmf-data",
        "sha256_metadata": VALID_SHA256,
        "sha256_data": VALID_SHA256,
        "sample_format": "cf32_le",
        "sample_rate_hz": 20_000_000.0,
        "sample_count": 20_000_000,
        "duration_s": 1.0,
        "access_classification": AccessClassification.RESTRICTED,
    }
    kwargs.update(overrides)
    return kwargs


def make_iq_recording(**overrides: Any) -> IQRecording:
    return IQRecording(**iq_recording_kwargs(**overrides))


def recording_reference(recording_id: UUID | None = None, version: int = 1) -> RecordingReference:
    return RecordingReference(recording_id=recording_id or uuid4(), version=version)


def rf_emission_kwargs(
    recording: RecordingReference | None = None, **overrides: Any
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"recording": recording or recording_reference()}
    kwargs.update(overrides)
    return kwargs


def frequency_behaviour_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "mode": FrequencySwitchingMode.SCRIPTED,
        "scripted_changes": [
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_412_000_000.0)
        ],
    }
    kwargs.update(overrides)
    return kwargs


def rf_band_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"freq_min_hz": 2_400_000_000.0, "freq_max_hz": 2_483_500_000.0}
    kwargs.update(overrides)
    return kwargs


def drone_rf_link_kwargs(
    recording: RecordingReference | None = None, **overrides: Any
) -> dict[str, Any]:
    ref = recording or recording_reference()
    kwargs: dict[str, Any] = {
        "role": RfLinkRole.C2,
        "band": RfBand(**rf_band_kwargs()),
        "frequency_behaviour": FrequencyBehaviour(**frequency_behaviour_kwargs()),
        "emissions": [RfEmission(**rf_emission_kwargs(recording=ref))],
    }
    kwargs.update(overrides)
    return kwargs


def make_drone_rf_link(
    recording: RecordingReference | None = None, **overrides: Any
) -> DroneRfLink:
    return DroneRfLink(**drone_rf_link_kwargs(recording=recording, **overrides))


def waypoint(sequence_index: int, lon: float, lat: float, altitude_m: float = 100.0) -> Waypoint:
    return Waypoint(
        sequence_index=sequence_index,
        position=geo_point(lon, lat),
        altitude_m=altitude_m,
        altitude_reference=AltitudeReference.AGL,
    )


def trajectory_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "template": MissionTemplate.WAYPOINT_TRANSIT,
        "waypoints": [waypoint(0, 13.40, 52.52), waypoint(1, 13.45, 52.53)],
        "default_speed_mps": 12.0,
    }
    kwargs.update(overrides)
    return kwargs


def drone_mission_kwargs(
    recording: RecordingReference | None = None, **overrides: Any
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": "recon-1",
        "platform": Platform(
            name="Generic Quad", category=PlatformCategory.MULTIROTOR, max_speed_mps=18.0
        ),
        "trajectory": Trajectory(**trajectory_kwargs()),
        "start_policy": MissionStartPolicy.AT_SCENARIO_START,
        "rf_links": [make_drone_rf_link(recording=recording)],
    }
    kwargs.update(overrides)
    return kwargs


def make_drone_mission(
    recording: RecordingReference | None = None, **overrides: Any
) -> DroneMission:
    return DroneMission(**drone_mission_kwargs(recording=recording, **overrides))


def make_receiver(receiver_type: ReceiverType = ReceiverType.MONITOR, **overrides: Any) -> Receiver:
    kwargs: dict[str, Any] = {
        "name": "site-alpha",
        "receiver_type": receiver_type,
        "position": geo_point(13.42, 52.50),
    }
    if receiver_type in (ReceiverType.TDOA, ReceiverType.AOA_DOA):
        kwargs["array_group_id"] = uuid4()
    if receiver_type == ReceiverType.AOA_DOA:
        kwargs["element_local_offset_m"] = (0.0, 0.0, 0.0)
    kwargs.update(overrides)
    return Receiver(**kwargs)


def make_scenario(**overrides: Any) -> Scenario:
    kwargs: dict[str, Any] = {
        "name": "urban-recon",
        "owner": "test-operator",
        "area_of_operation": area_polygon(),
    }
    kwargs.update(overrides)
    return Scenario(**kwargs)


def make_zone(**overrides: Any) -> Zone:
    kwargs: dict[str, Any] = {"zone_type": ZoneType.OPERATIONAL_AREA, "polygon": area_polygon()}
    kwargs.update(overrides)
    return Zone(**kwargs)


def scenario_version_kwargs(**overrides: Any) -> dict[str, Any]:
    recording = make_iq_recording()
    ref = recording.reference()
    mission = make_drone_mission(recording=ref)
    kwargs: dict[str, Any] = {
        "id": uuid4(),
        "scenario_id": uuid4(),
        "version_number": 1,
        "zones": [make_zone()],
        "missions": [mission],
        "receivers": [make_receiver()],
        "timeline_events": [AbsoluteTimelineEvent(scenario_time_offset=timedelta(seconds=5))],
        "recordings": [ref],
        "author": "test-operator",
    }
    kwargs.update(overrides)
    return kwargs


def make_scenario_version(**overrides: Any) -> ScenarioVersion:
    return ScenarioVersion(**scenario_version_kwargs(**overrides))
