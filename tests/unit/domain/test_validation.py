"""Tests for cross-entity ScenarioVersion validation."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from factories import (
    drone_mission_kwargs,
    drone_rf_link_kwargs,
    make_receiver,
    make_zone,
    recording_reference,
    scenario_version_kwargs,
    waypoint,
)

from rogue.domain.common import GeoPolygon
from rogue.domain.mission import DroneMission, MissionTemplate, Trajectory
from rogue.domain.receiver import ReceiverType
from rogue.domain.recording import RecordingReference
from rogue.domain.rf import DroneRfLink, RfEmission, ZoneTriggerPolicy
from rogue.domain.scenario import ScenarioVersion, ZoneType
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


def test_coherent_link_with_unresolvable_array_group_is_blocking() -> None:
    ref = recording_reference()
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, array_group_id=uuid4()))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], receivers=[])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "coherent_group_unresolvable" in codes


def test_coherent_link_referencing_only_one_array_receiver_is_blocking() -> None:
    ref = recording_reference()
    group_id = uuid4()
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, array_group_id=group_id))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    receiver = make_receiver(ReceiverType.TDOA, array_group_id=group_id)
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], receivers=[receiver])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "coherent_group_unresolvable" in codes


def test_coherent_link_with_valid_tdoa_array_group_is_not_blocking() -> None:
    ref = recording_reference()
    group_id = uuid4()
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, array_group_id=group_id))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    receivers = [
        make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=0),
        make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=1),
    ]
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], receivers=receivers)
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "coherent_group_unresolvable" not in codes


def test_empty_scenario_produces_warning_not_blocking() -> None:
    kwargs = scenario_version_kwargs(missions=[], receivers=[], recordings=[], timeline_events=[])
    version = ScenarioVersion(**kwargs)

    findings = validate_scenario_version(version)

    warnings = [f for f in findings if f.severity == ValidationSeverity.WARNING]
    assert any(f.code == "empty_scenario" for f in warnings)
    assert not any(f.severity == ValidationSeverity.BLOCKING for f in findings)


def test_zone_trigger_with_unresolvable_zone_is_blocking() -> None:
    ref = recording_reference()
    emission = RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=uuid4()))
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=[emission]))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(**scenario_version_kwargs(missions=[mission], recordings=[ref]))

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_reference_unresolvable" in codes


def test_zone_trigger_referencing_non_trigger_zone_is_blocking() -> None:
    ref = recording_reference()
    zone = make_zone(zone_type=ZoneType.OPERATIONAL_AREA)
    emission = RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone.id))
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=[emission]))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_reference_unresolvable" in codes


def test_zone_trigger_referencing_valid_trigger_zone_is_not_blocking() -> None:
    ref = recording_reference()
    zone = make_zone(zone_type=ZoneType.TRIGGER)
    emission = RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone.id))
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=[emission]))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_reference_unresolvable" not in codes


def test_observed_by_receiver_unresolvable_is_blocking() -> None:
    ref = recording_reference()
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, observed_by_receiver_id=uuid4()))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], receivers=[])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "observed_by_receiver_unresolvable" in codes


def test_observed_by_receiver_referencing_non_monitor_is_blocking() -> None:
    ref = recording_reference()
    group_id = uuid4()
    receiver = make_receiver(ReceiverType.TDOA, array_group_id=group_id)
    link = DroneRfLink(
        **drone_rf_link_kwargs(recording=ref, observed_by_receiver_id=receiver.id)
    )
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], receivers=[receiver])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "observed_by_receiver_unresolvable" in codes


def test_observed_by_receiver_referencing_monitor_is_not_blocking() -> None:
    ref = recording_reference()
    receiver = make_receiver(ReceiverType.MONITOR)
    link = DroneRfLink(
        **drone_rf_link_kwargs(recording=ref, observed_by_receiver_id=receiver.id)
    )
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], receivers=[receiver])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "observed_by_receiver_unresolvable" not in codes


def _straight_line_mission(
    ref: RecordingReference, from_lon_lat: tuple[float, float], to_lon_lat: tuple[float, float]
) -> DroneMission:
    trajectory = Trajectory(
        template=MissionTemplate.WAYPOINT_TRANSIT,
        waypoints=[
            waypoint(0, *from_lon_lat),
            waypoint(1, *to_lon_lat),
        ],
        default_speed_mps=10.0,
    )
    return DroneMission(**drone_mission_kwargs(recording=ref, trajectory=trajectory))


def test_mission_trajectory_entering_no_fly_zone_is_blocking() -> None:
    ref = recording_reference()
    no_fly_zone = make_zone(
        zone_type=ZoneType.NO_FLY,
        polygon=GeoPolygon(
            coordinates=[
                [
                    (13.39, 52.499),
                    (13.43, 52.499),
                    (13.43, 52.501),
                    (13.39, 52.501),
                    (13.39, 52.499),
                ]
            ]
        ),
    )
    mission = _straight_line_mission(ref, (13.40, 52.50), (13.42, 52.50))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[no_fly_zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "no_fly_trajectory_containment" in codes


def test_mission_trajectory_avoiding_no_fly_zone_is_not_blocking() -> None:
    ref = recording_reference()
    no_fly_zone = make_zone(
        zone_type=ZoneType.NO_FLY,
        polygon=GeoPolygon(
            coordinates=[[(20.0, 10.0), (21.0, 10.0), (21.0, 11.0), (20.0, 11.0), (20.0, 10.0)]]
        ),
    )
    mission = _straight_line_mission(ref, (13.40, 52.50), (13.42, 52.50))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[no_fly_zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "no_fly_trajectory_containment" not in codes


def test_orbit_mission_entering_no_fly_zone_is_blocking() -> None:
    # ORBIT's two waypoints are a center/radius reference, not path points —
    # both sit far from the zone below, but the real circular path (radius
    # 2000m around the center) sweeps through it. A chord-based check
    # between the raw waypoints would miss this entirely.
    ref = recording_reference()
    orbit_trajectory = Trajectory(
        template=MissionTemplate.ORBIT,
        waypoints=[waypoint(0, 13.40, 52.50), waypoint(1, 13.401, 52.501)],
        default_speed_mps=10.0,
        template_parameters={"radius_m": 2000.0},
    )
    mission = DroneMission(**drone_mission_kwargs(recording=ref, trajectory=orbit_trajectory))
    no_fly_zone = make_zone(
        zone_type=ZoneType.NO_FLY,
        polygon=GeoPolygon(
            coordinates=[
                [(13.42, 52.49), (13.44, 52.49), (13.44, 52.51), (13.42, 52.51), (13.42, 52.49)]
            ]
        ),
    )
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[no_fly_zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "no_fly_trajectory_containment" in codes


def test_orbit_mission_avoiding_no_fly_zone_is_not_blocking() -> None:
    ref = recording_reference()
    orbit_trajectory = Trajectory(
        template=MissionTemplate.ORBIT,
        waypoints=[waypoint(0, 13.40, 52.50), waypoint(1, 13.401, 52.501)],
        default_speed_mps=10.0,
        template_parameters={"radius_m": 50.0},
    )
    mission = DroneMission(**drone_mission_kwargs(recording=ref, trajectory=orbit_trajectory))
    far_zone = make_zone(
        zone_type=ZoneType.NO_FLY,
        polygon=GeoPolygon(
            coordinates=[[(20.0, 10.0), (21.0, 10.0), (21.0, 11.0), (20.0, 11.0), (20.0, 10.0)]]
        ),
    )
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[far_zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "no_fly_trajectory_containment" not in codes


def test_mission_trajectory_crossing_antimeridian_does_not_false_positive() -> None:
    # A short ~0.2 deg hop across the +/-180 date line. A zone at longitude
    # 0 is nowhere near the true short path; naive linear lon interpolation
    # would sweep the "long way" through 0 and wrongly flag it.
    ref = recording_reference()
    far_side_zone = make_zone(
        zone_type=ZoneType.NO_FLY,
        polygon=GeoPolygon(
            coordinates=[[(-1.0, 9.0), (1.0, 9.0), (1.0, 11.0), (-1.0, 11.0), (-1.0, 9.0)]]
        ),
    )
    mission = _straight_line_mission(ref, (179.9, 10.0), (-179.9, 10.0))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[far_side_zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "no_fly_trajectory_containment" not in codes


def test_leg_fully_inside_no_fly_zone_produces_exactly_one_finding() -> None:
    ref = recording_reference()
    no_fly_zone = make_zone(
        zone_type=ZoneType.NO_FLY,
        polygon=GeoPolygon(
            coordinates=[
                [
                    (13.39, 52.499),
                    (13.43, 52.499),
                    (13.43, 52.501),
                    (13.39, 52.501),
                    (13.39, 52.499),
                ]
            ]
        ),
    )
    mission = _straight_line_mission(ref, (13.40, 52.50), (13.42, 52.50))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[no_fly_zone])
    )

    findings = validate_scenario_version(version)

    matching = [f for f in findings if f.code == "no_fly_trajectory_containment"]
    assert len(matching) == 1


def test_duplicate_zone_trigger_zone_id_on_same_link_is_blocking() -> None:
    ref = recording_reference()
    zone = make_zone(zone_type=ZoneType.TRIGGER)
    emissions = [
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone.id)),
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone.id)),
    ]
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=emissions))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_duplicate_zone" in codes


def test_zone_trigger_with_loop_emission_on_same_link_is_blocking() -> None:
    ref = recording_reference()
    zone = make_zone(zone_type=ZoneType.TRIGGER)
    emissions = [
        RfEmission(recording=ref, start_offset=timedelta(0), loop=True),
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone.id)),
    ]
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=emissions))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(missions=[mission], recordings=[ref], zones=[zone])
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_overlaps_loop" in codes


def test_zone_trigger_different_zones_without_loop_is_not_blocking() -> None:
    # Two distinct zone_ids are never BLOCKING regardless of their
    # geometry — at most a WARNING (zone_trigger_zones_may_overlap, see
    # below) since ADR-018's polygon-intersection check is advisory, not a
    # certainty (CLAUDE.md rule 5: overlap may be intentional/never
    # actually realized). Both zones happen to share the same default
    # polygon here, so the WARNING does fire — asserted explicitly.
    ref = recording_reference()
    zone_a = make_zone(zone_type=ZoneType.TRIGGER)
    zone_b = make_zone(zone_type=ZoneType.TRIGGER)
    emissions = [
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone_a.id)),
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone_b.id)),
    ]
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=emissions))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(
            missions=[mission], recordings=[ref], zones=[zone_a, zone_b]
        )
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_duplicate_zone" not in codes
    assert "zone_trigger_overlaps_loop" not in codes
    warning_codes = {f.code for f in findings if f.severity == ValidationSeverity.WARNING}
    assert "zone_trigger_zones_may_overlap" in warning_codes


def test_zone_trigger_disjoint_zones_produce_no_overlap_warning() -> None:
    ref = recording_reference()
    zone_a = make_zone(
        zone_type=ZoneType.TRIGGER,
        polygon=GeoPolygon(
            coordinates=[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]]
        ),
    )
    zone_b = make_zone(
        zone_type=ZoneType.TRIGGER,
        polygon=GeoPolygon(
            coordinates=[[(5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0)]]
        ),
    )
    emissions = [
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone_a.id)),
        RfEmission(recording=ref, zone_trigger=ZoneTriggerPolicy(zone_id=zone_b.id)),
    ]
    link = DroneRfLink(**drone_rf_link_kwargs(recording=ref, emissions=emissions))
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link]))
    version = ScenarioVersion(
        **scenario_version_kwargs(
            missions=[mission], recordings=[ref], zones=[zone_a, zone_b]
        )
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings}
    assert "zone_trigger_zones_may_overlap" not in codes


def test_zone_trigger_overlapping_zones_across_different_links_is_not_flagged() -> None:
    # The overlap checks are scoped to a single RfLink (same rationale as
    # overlapping_emissions/zone_trigger_duplicate_zone/
    # zone_trigger_overlaps_loop): independent links may legitimately
    # overlap in time (CLAUDE.md rule 5).
    ref = recording_reference()
    zone_a = make_zone(zone_type=ZoneType.TRIGGER)
    zone_b = make_zone(zone_type=ZoneType.TRIGGER)
    trigger_a = ZoneTriggerPolicy(zone_id=zone_a.id)
    trigger_b = ZoneTriggerPolicy(zone_id=zone_b.id)
    link_a = DroneRfLink(
        **drone_rf_link_kwargs(
            recording=ref,
            emissions=[RfEmission(recording=ref, zone_trigger=trigger_a)],
        )
    )
    link_b = DroneRfLink(
        **drone_rf_link_kwargs(
            recording=ref,
            emissions=[RfEmission(recording=ref, zone_trigger=trigger_b)],
        )
    )
    mission = DroneMission(**drone_mission_kwargs(recording=ref, rf_links=[link_a, link_b]))
    version = ScenarioVersion(
        **scenario_version_kwargs(
            missions=[mission], recordings=[ref], zones=[zone_a, zone_b]
        )
    )

    findings = validate_scenario_version(version)

    codes = {f.code for f in findings}
    assert "zone_trigger_zones_may_overlap" not in codes
