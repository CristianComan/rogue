"""Minimal domain object builders for persistence tests.

Deliberately not shared with tests/unit/domain/factories.py: pytest's
rootdir-based import (no __init__.py in either directory) makes each
test directory its own top-level import namespace, so cross-directory
imports aren't reliable when a test subset runs in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

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
from rogue.domain.scenario import Scenario, ScenarioDraft


def area_polygon() -> GeoPolygon:
    ring = [(13.0, 52.0), (13.5, 52.0), (13.5, 52.5), (13.0, 52.5), (13.0, 52.0)]
    return GeoPolygon(coordinates=[ring])


def make_scenario(**overrides: Any) -> Scenario:
    now = datetime.now(UTC)
    kwargs: dict[str, Any] = {
        "name": "persistence-test-scenario",
        "owner": "test-operator",
        "tags": ["lab-a"],
        "area_of_operation": area_polygon(),
        "created_at": now,
        "updated_at": now,
    }
    kwargs.update(overrides)
    return Scenario(**kwargs)


def make_draft(scenario_id: UUID, **overrides: Any) -> ScenarioDraft:
    now = datetime.now(UTC)
    kwargs: dict[str, Any] = {
        "scenario_id": scenario_id,
        "author": "test-operator",
        "created_at": now,
        "updated_at": now,
    }
    kwargs.update(overrides)
    return ScenarioDraft(**kwargs)


def recording_reference() -> RecordingReference:
    return RecordingReference(recording_id=uuid4(), version=1)


def make_recording(**overrides: Any) -> IQRecording:
    kwargs: dict[str, Any] = {
        "version": 1,
        "metadata_object_key": "recordings/demo/v1.sigmf-meta",
        "data_object_key": "recordings/demo/v1.sigmf-data",
        "sha256_metadata": "a" * 64,
        "sha256_data": "a" * 64,
        "sample_format": "cf32_le",
        "sample_rate_hz": 2_000_000.0,
        "sample_count": 2_000_000,
        "duration_s": 1.0,
        "access_classification": AccessClassification.RESTRICTED,
    }
    kwargs.update(overrides)
    return IQRecording(**kwargs)


def make_mission(recording: RecordingReference, **overrides: Any) -> DroneMission:
    kwargs: dict[str, Any] = {
        "name": "recon-1",
        "platform": Platform(
            name="Generic Quad", category=PlatformCategory.MULTIROTOR, max_speed_mps=18.0
        ),
        "trajectory": Trajectory(
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
        "rf_links": [
            DroneRfLink(
                role=RfLinkRole.C2,
                band=RfBand(freq_min_hz=2_400_000_000.0, freq_max_hz=2_483_500_000.0),
                frequency_behaviour=FrequencyBehaviour(
                    mode=FrequencySwitchingMode.SCRIPTED,
                    scripted_changes=[
                        ScriptedFrequencyChange(
                            at_offset=timedelta(0), frequency_hz=2_412_000_000.0
                        )
                    ],
                ),
                emissions=[RfEmission(recording=recording)],
            )
        ],
    }
    kwargs.update(overrides)
    return DroneMission(**kwargs)
