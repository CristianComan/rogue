"""Tests for cross-entity ScenarioVersion validation."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from factories import (
    drone_mission_kwargs,
    drone_rf_link_kwargs,
    recording_reference,
    scenario_version_kwargs,
)

from rogue.domain.mission import DroneMission
from rogue.domain.rf import DroneRfLink, RfEmission
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.timeline import MissionRelativeAnchor, MissionRelativeTimelineEvent
from rogue.domain.validation import ValidationSeverity, validate_scenario_version


def test_valid_scenario_version_has_no_blocking_findings() -> None:
    version = ScenarioVersion(**scenario_version_kwargs())
    findings = validate_scenario_version(version)
    assert all(f.severity != ValidationSeverity.BLOCKING for f in findings)


def test_dangling_mission_reference_on_timeline_event_is_blocking() -> None:
    dangling_event = MissionRelativeTimelineEvent(
        mission_id=uuid4(), anchor=MissionRelativeAnchor.MISSION_START
    )
    version = ScenarioVersion(**scenario_version_kwargs(timeline_events=[dangling_event]))

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "dangling_mission_reference" in codes


def test_dangling_waypoint_reference_is_blocking() -> None:
    kwargs = scenario_version_kwargs()
    mission = kwargs["missions"][0]
    event = MissionRelativeTimelineEvent(
        mission_id=mission.id,
        anchor=MissionRelativeAnchor.WAYPOINT,
        waypoint_sequence_index=999,
        offset=timedelta(0),
    )
    kwargs["timeline_events"] = [event]

    findings = validate_scenario_version(ScenarioVersion(**kwargs))

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "dangling_waypoint_reference" in codes


def test_overlapping_emissions_is_blocking() -> None:
    ref = recording_reference()
    overlapping = [
        RfEmission(
            recording=ref, start_offset=timedelta(0), duration_override=timedelta(seconds=10)
        ),
        RfEmission(
            recording=ref,
            start_offset=timedelta(seconds=5),
            duration_override=timedelta(seconds=10),
        ),
    ]
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=overlapping))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(**scenario_version_kwargs(missions=[mission], recordings=[ref]))

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "overlapping_emissions" in codes


def test_sequential_non_overlapping_emissions_is_not_blocking() -> None:
    ref = recording_reference()
    sequential = [
        RfEmission(
            recording=ref, start_offset=timedelta(0), duration_override=timedelta(seconds=5)
        ),
        RfEmission(
            recording=ref,
            start_offset=timedelta(seconds=5),
            duration_override=timedelta(seconds=5),
        ),
    ]
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=sequential))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(**scenario_version_kwargs(missions=[mission], recordings=[ref]))

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "overlapping_emissions" not in codes


def test_silence_span_does_not_trigger_dangling_recording_reference() -> None:
    ref = recording_reference()
    silence = RfEmission(
        recording=None, start_offset=timedelta(0), duration_override=timedelta(seconds=5)
    )
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=[silence]))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(**scenario_version_kwargs(missions=[mission], recordings=[ref]))

    findings = validate_scenario_version(version)

    assert all(f.severity != ValidationSeverity.BLOCKING for f in findings)


def test_empty_scenario_produces_warning_not_blocking() -> None:
    kwargs = scenario_version_kwargs(missions=[], receivers=[], recordings=[], timeline_events=[])
    version = ScenarioVersion(**kwargs)

    findings = validate_scenario_version(version)

    warnings = [f for f in findings if f.severity == ValidationSeverity.WARNING]
    assert any(f.code == "empty_scenario" for f in warnings)
    assert not any(f.severity == ValidationSeverity.BLOCKING for f in findings)
