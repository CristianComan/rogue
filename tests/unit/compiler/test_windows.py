"""Unit tests for rogue.compiler.windows — pure functions, no DB."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from compiler_factories import (
    make_capability_profile,
    make_link,
    make_mission,
    make_receiver,
    make_recording,
    make_scenario_version,
    recording_key,
)

from rogue.compiler.windows import compute_rf_windows
from rogue.domain.common import GeoPoint, GeoPolygon
from rogue.domain.mission import (
    AltitudeReference,
    MissionStartPolicy,
    MissionTemplate,
    Trajectory,
    Waypoint,
)
from rogue.domain.receiver import ReceiverType
from rogue.domain.rf import RfBand, RfEmission, ScriptedFrequencyChange, ZoneTriggerPolicy
from rogue.domain.scenario import Zone, ZoneType
from rogue.domain.validation import ValidationSeverity

# A ~1000m leg due north at 10 m/s (~100s transit) — mirrors
# tests/unit/domain/test_mission_evaluator.py's STRAIGHT_LEG fixture.
_STRAIGHT_LEG = Trajectory(
    template=MissionTemplate.WAYPOINT_TRANSIT,
    waypoints=[
        Waypoint(
            sequence_index=0,
            position=GeoPoint(coordinates=(13.4, 52.5)),
            altitude_m=100.0,
            altitude_reference=AltitudeReference.AGL,
        ),
        Waypoint(
            sequence_index=1,
            position=GeoPoint(coordinates=(13.4, 52.509)),
            altitude_m=100.0,
            altitude_reference=AltitudeReference.AGL,
        ),
    ],
    default_speed_mps=10.0,
)

# Covers roughly the middle third of _STRAIGHT_LEG's transit.
_MID_LEG_ZONE = Zone(
    zone_type=ZoneType.TRIGGER,
    polygon=GeoPolygon(
        coordinates=[
            [(13.39, 52.503), (13.41, 52.503), (13.41, 52.506), (13.39, 52.506), (13.39, 52.503)]
        ]
    ),
)


def test_single_link_produces_one_window_spanning_full_duration() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=100.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=20.0, capability_profile=profile
    )

    assert findings == []
    assert len(windows) == 1
    window = windows[0]
    assert window.start_seconds == 0.0
    assert window.end_seconds == 20.0
    assert window.center_frequency_hz == 2_412_000_000.0
    assert len(window.channels) == 1


def test_two_close_links_share_one_window() -> None:
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    link_a = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_410_000_000.0)
        ],
    )
    link_b = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_410_500_000.0)
        ],
    )
    version = make_scenario_version([make_mission([link_a, link_b])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    # The two links' occupied bands legitimately overlap (CLAUDE.md rule 5):
    # M5's spectral_overlap WARNING is expected here, never BLOCKING.
    assert all(f.severity != ValidationSeverity.BLOCKING for f in findings)
    assert len(windows) == 1
    assert len(windows[0].channels) == 2


def test_far_apart_links_produce_separate_windows() -> None:
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    band = RfBand(freq_min_hz=1_000_000_000.0, freq_max_hz=6_000_000_000.0)
    link_a = make_link(
        recording.reference(),
        band=band,
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_400_000_000.0)
        ],
    )
    link_b = make_link(
        recording.reference(),
        band=band,
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=5_000_000_000.0)
        ],
    )
    version = make_scenario_version([make_mission([link_a, link_b])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert findings == []
    assert len(windows) == 2
    assert all(len(w.channels) == 1 for w in windows)


def test_window_splits_when_frequency_changes_mid_horizon() -> None:
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    band = RfBand(freq_min_hz=1_000_000_000.0, freq_max_hz=6_000_000_000.0)
    link = make_link(
        recording.reference(),
        band=band,
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_400_000_000.0),
            ScriptedFrequencyChange(at_offset=timedelta(seconds=5), frequency_hz=5_000_000_000.0),
        ],
    )
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert findings == []
    assert len(windows) == 2
    windows.sort(key=lambda w: w.start_seconds)
    assert windows[0].start_seconds == 0.0
    assert windows[0].end_seconds == 5.0
    assert windows[1].start_seconds == 5.0
    assert windows[1].end_seconds == 10.0


def test_bandwidth_exceeding_every_channel_is_blocking() -> None:
    # wider than any configured channel
    recording = make_recording(sample_rate_hz=50_000_000.0, duration_s=100.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert windows == []
    codes = [f.code for f in findings]
    assert "rf_window_infeasible" in codes
    finding = next(f for f in findings if f.code == "rf_window_infeasible")
    assert finding.severity == ValidationSeverity.BLOCKING


def test_coherent_link_expands_into_separate_windows_per_element() -> None:
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    group_id = uuid4()
    link = make_link(recording.reference(), array_group_id=group_id)
    mission = make_mission([link])
    rx_a = make_receiver(ReceiverType.AOA_DOA, array_group_id=group_id, element_index=0)
    rx_b = make_receiver(ReceiverType.AOA_DOA, array_group_id=group_id, element_index=1)
    version = make_scenario_version([mission], [recording.reference()], receivers=[rx_a, rx_b])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert findings == []
    # Same frequency, same link — would normally merge into one window
    # (like test_two_close_links_share_one_window above); the coherent
    # group guard must keep them separate since each needs its own
    # physical channel.
    assert len(windows) == 2
    assert all(len(w.channels) == 1 for w in windows)
    receiver_ids = {w.channels[0].array_element_receiver_id for w in windows}
    assert receiver_ids == {rx_a.id, rx_b.id}
    window_keys = {w.window_key for w in windows}
    assert len(window_keys) == 2  # per-element window_key stays unique
    assert all(w.channels[0].coherent_group_id == group_id for w in windows)


def test_non_coherent_link_unaffected_by_coherent_group_support() -> None:
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    link = make_link(recording.reference())  # no array_group_id
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert findings == []
    assert len(windows) == 1
    assert windows[0].channels[0].coherent_group_id is None
    assert windows[0].channels[0].doppler_schedule is None


# --- continuous Doppler schedule (M12, ADR-013) -----------------------------


def test_coherent_channels_carry_a_doppler_schedule_spanning_the_whole_window() -> None:
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    group_id = uuid4()
    link = make_link(recording.reference(), array_group_id=group_id)
    mission = make_mission([link])
    rx_a = make_receiver(ReceiverType.AOA_DOA, array_group_id=group_id, element_index=0)
    rx_b = make_receiver(ReceiverType.AOA_DOA, array_group_id=group_id, element_index=1)
    version = make_scenario_version([mission], [recording.reference()], receivers=[rx_a, rx_b])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert findings == []
    for window in windows:
        schedule = window.channels[0].doppler_schedule
        assert schedule is not None
        assert schedule[0].t_offset_seconds == 0.0
        assert schedule[-1].t_offset_seconds == window.end_seconds - window.start_seconds


def test_tdoa_elements_get_a_doppler_schedule_despite_having_no_phase() -> None:
    """Doppler needs no element_local_offset_m — unlike phase, it's
    computed for TDOA elements too."""
    recording = make_recording(sample_rate_hz=1_000_000.0, duration_s=100.0)
    group_id = uuid4()
    link = make_link(recording.reference(), array_group_id=group_id)
    mission = make_mission([link])
    rx_a = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=0)
    rx_b = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=1)
    version = make_scenario_version([mission], [recording.reference()], receivers=[rx_a, rx_b])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert findings == []
    for window in windows:
        assert window.channels[0].phase_offset_rad is None
        assert window.channels[0].doppler_schedule is not None


def test_idle_link_contributes_no_window() -> None:
    recording = make_recording(duration_s=1.0)
    link = make_link(
        recording.reference(),
        emissions=[
            RfEmission(recording=recording.reference(), start_offset=timedelta(seconds=100))
        ],
    )
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=10.0, capability_profile=profile
    )

    assert windows == []
    assert findings == []


# --------------------------------------------------- zone_trigger (ADR-015 follow-up)


def test_zone_triggered_emission_produces_window_only_during_crossing_interval() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=1.0)
    zone_trigger = ZoneTriggerPolicy(zone_id=_MID_LEG_ZONE.id)
    link = make_link(
        recording.reference(),
        emissions=[RfEmission(recording=recording.reference(), zone_trigger=zone_trigger)],
    )
    mission = make_mission([link], trajectory=_STRAIGHT_LEG)
    version = make_scenario_version([mission], [recording.reference()], zones=[_MID_LEG_ZONE])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=100.0, capability_profile=profile
    )

    assert findings == []
    assert len(windows) == 1
    window = windows[0]
    # Gated to the crossing interval, not the full [0, 100) compile horizon.
    assert window.start_seconds > 0.0
    assert window.end_seconds < 100.0
    assert window.channels[0].emission_id == link.emissions[0].id


def test_zone_triggered_emission_unsupported_template_is_blocking() -> None:
    unsupported_trajectory = Trajectory(
        template=MissionTemplate.RACETRACK,
        waypoints=_STRAIGHT_LEG.waypoints,
        default_speed_mps=10.0,
    )
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=1.0)
    zone_trigger = ZoneTriggerPolicy(zone_id=_MID_LEG_ZONE.id)
    link = make_link(
        recording.reference(),
        emissions=[RfEmission(recording=recording.reference(), zone_trigger=zone_trigger)],
    )
    mission = make_mission([link], trajectory=unsupported_trajectory)
    version = make_scenario_version([mission], [recording.reference()], zones=[_MID_LEG_ZONE])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=100.0, capability_profile=profile
    )

    assert windows == []
    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_position_unresolvable" in codes


def test_zone_triggered_emission_unresolvable_mission_surfaces_even_with_delayed_start() -> None:
    # A delayed AT_TIME_OFFSET start means evaluate_mission_position's "before
    # start" early return covers every boundary _boundary_seconds discovers on
    # its own ({0.0, duration_s}), so the unsupported RACETRACK template is
    # never actually reached at either instant — this must still surface as a
    # BLOCKING finding rather than silently producing no windows and no
    # findings at all (see ADR-016).
    unsupported_trajectory = Trajectory(
        template=MissionTemplate.RACETRACK,
        waypoints=_STRAIGHT_LEG.waypoints,
        default_speed_mps=10.0,
    )
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=1.0)
    zone_trigger = ZoneTriggerPolicy(zone_id=_MID_LEG_ZONE.id)
    link = make_link(
        recording.reference(),
        emissions=[RfEmission(recording=recording.reference(), zone_trigger=zone_trigger)],
    )
    mission = make_mission(
        [link],
        trajectory=unsupported_trajectory,
        start_policy=MissionStartPolicy.AT_TIME_OFFSET,
        start_time_offset=timedelta(seconds=50),
    )
    version = make_scenario_version([mission], [recording.reference()], zones=[_MID_LEG_ZONE])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=100.0, capability_profile=profile
    )

    assert windows == []
    codes = {f.code for f in findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_position_unresolvable" in codes


def test_observed_by_receiver_id_survives_into_composite_channel() -> None:
    receiver_id = uuid4()
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=100.0)
    link = make_link(recording.reference(), observed_by_receiver_id=receiver_id)
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    windows, findings = compute_rf_windows(
        version, recordings, duration_s=20.0, capability_profile=profile
    )

    assert findings == []
    assert windows[0].channels[0].observed_by_receiver_id == receiver_id
