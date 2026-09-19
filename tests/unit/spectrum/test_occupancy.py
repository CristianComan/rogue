"""Unit tests for rogue.spectrum.occupancy — pure functions, no DB."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from spectrum_factories import (
    make_link,
    make_mission,
    make_recording,
    make_scenario_version,
    recording_key,
)

from rogue.domain.common import GeoPoint, GeoPolygon
from rogue.domain.mission import (
    AltitudeReference,
    MissionTemplate,
    Trajectory,
    Waypoint,
)
from rogue.domain.recording import RecordingReference
from rogue.domain.rf import (
    DroneRfLink,
    FrequencySwitchingMode,
    RfBand,
    RfEmission,
    ScriptedFrequencyChange,
    ZoneTriggerPolicy,
)
from rogue.domain.scenario import Zone, ZoneType
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.occupancy import (
    active_emission_at,
    compute_spectrum_state,
    resolve_frequency_hz,
)

# A ~1000m leg due north (mirrors tests/unit/domain/test_mission_evaluator.py's
# STRAIGHT_LEG) — easy to reason about crossing timing at 10 m/s (~100s transit).
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

# ------------------------------------------------------------- resolve_frequency_hz


def test_resolve_frequency_hz_scripted_before_first_change_uses_band_min() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(seconds=10), frequency_hz=2_450_000_000.0)
        ],
    )

    resolution = resolve_frequency_hz(link, at_seconds=5.0)

    assert resolution.resolved
    assert resolution.frequency_hz == link.band.freq_min_hz


def test_resolve_frequency_hz_scripted_after_change() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_410_000_000.0),
            ScriptedFrequencyChange(at_offset=timedelta(seconds=10), frequency_hz=2_450_000_000.0),
        ],
    )

    assert resolve_frequency_hz(link, at_seconds=9.9).frequency_hz == 2_410_000_000.0
    assert resolve_frequency_hz(link, at_seconds=10.0).frequency_hz == 2_450_000_000.0


def test_resolve_frequency_hz_probabilistic_deterministic_same_seed() -> None:
    recording = make_recording()
    band = RfBand(
        freq_min_hz=2_400_000_000.0,
        freq_max_hz=2_483_500_000.0,
        allowed_channels_hz=[2_412_000_000.0, 2_437_000_000.0, 2_462_000_000.0],
    )
    link_a = make_link(
        recording.reference(),
        mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE,
        band=band,
        random_seed=7,
        mean_dwell_s=2.0,
    )
    link_b = make_link(
        recording.reference(),
        mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE,
        band=band,
        random_seed=7,
        mean_dwell_s=2.0,
    )

    resolution_a = resolve_frequency_hz(link_a, at_seconds=30.0)
    resolution_b = resolve_frequency_hz(link_b, at_seconds=30.0)

    assert resolution_a.resolved and resolution_b.resolved
    assert resolution_a.frequency_hz == resolution_b.frequency_hz
    assert resolution_a.frequency_hz in band.allowed_channels_hz


def test_resolve_frequency_hz_probabilistic_empty_channels_unresolved() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE,
        random_seed=1,
        mean_dwell_s=2.0,
    )  # default band has no allowed_channels_hz

    resolution = resolve_frequency_hz(link, at_seconds=5.0)

    assert not resolution.resolved
    assert resolution.unresolved_reason is not None
    assert "allowed_channels_hz" in resolution.unresolved_reason


def test_resolve_frequency_hz_mission_triggered_unresolved() -> None:
    recording = make_recording()
    link = make_link(recording.reference(), mode=FrequencySwitchingMode.MISSION_TRIGGERED)

    resolution = resolve_frequency_hz(link, at_seconds=5.0)

    assert not resolution.resolved
    assert "mission" in (resolution.unresolved_reason or "").lower()


def test_resolve_frequency_hz_external_state_triggered_unresolved() -> None:
    recording = make_recording()
    link = make_link(recording.reference(), mode=FrequencySwitchingMode.EXTERNAL_STATE_TRIGGERED)

    resolution = resolve_frequency_hz(link, at_seconds=5.0)

    assert not resolution.resolved


# ----------------------------------------------------------------- active_emission_at


def test_active_emission_at_within_window() -> None:
    recording = make_recording(duration_s=10.0)
    link = make_link(
        recording.reference(),
        emissions=[RfEmission(recording=recording.reference(), start_offset=timedelta(seconds=5))],
    )
    mission = make_mission([link])
    recordings = {recording_key(recording.reference()): recording}

    assert active_emission_at(mission, link, 4.9, recordings, {}) is None
    assert active_emission_at(mission, link, 5.0, recordings, {}) is not None
    assert active_emission_at(mission, link, 14.9, recordings, {}) is not None
    assert active_emission_at(mission, link, 15.0, recordings, {}) is None


def test_active_emission_at_loop_repeats_indefinitely() -> None:
    recording = make_recording(duration_s=1.0)
    link = make_link(
        recording.reference(),
        emissions=[
            RfEmission(recording=recording.reference(), start_offset=timedelta(0), loop=True)
        ],
    )
    mission = make_mission([link])
    recordings = {recording_key(recording.reference()): recording}

    assert active_emission_at(mission, link, 999.0, recordings, {}) is not None


def test_active_emission_at_unknown_duration_assumed_active() -> None:
    """No duration_override and the recording isn't resolvable: conservatively active."""
    recording = make_recording()
    link = make_link(
        recording.reference(),
        emissions=[RfEmission(recording=recording.reference(), start_offset=timedelta(0))],
    )
    mission = make_mission([link])

    assert active_emission_at(mission, link, 999.0, recordings={}, zones_by_id={}) is not None


# ------------------------------------------------------------- compute_spectrum_state


def test_compute_spectrum_state_single_link_happy_path() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}

    state = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)

    assert len(state.occupied_bands) == 1
    band_result = state.occupied_bands[0]
    assert band_result.center_frequency_hz == 2_412_000_000.0
    assert band_result.bandwidth_hz == 2_000_000.0
    assert band_result.freq_min_hz == 2_411_000_000.0
    assert band_result.freq_max_hz == 2_413_000_000.0
    assert band_result.headroom_hz == (link.band.freq_max_hz - link.band.freq_min_hz) - 2_000_000.0
    assert state.findings == []


def test_compute_spectrum_state_recording_unavailable_warning() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        emissions=[
            RfEmission(
                recording=recording.reference(),
                start_offset=timedelta(0),
                duration_override=timedelta(seconds=5),
            )
        ],
    )
    version = make_scenario_version([make_mission([link])], [recording.reference()])

    state = compute_spectrum_state(version, at_seconds=0.0, recordings={})

    assert state.occupied_bands == []
    assert len(state.findings) == 1
    assert state.findings[0].code == "recording_unavailable"
    assert state.findings[0].severity == ValidationSeverity.WARNING


def test_compute_spectrum_state_bandwidth_exceeds_band_blocking() -> None:
    band = RfBand(freq_min_hz=2_400_000_000.0, freq_max_hz=2_402_000_000.0)
    recording = make_recording(sample_rate_hz=5_000_000.0)
    link = make_link(
        recording.reference(),
        band=band,
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_401_000_000.0)
        ],
    )
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}

    state = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)

    assert len(state.occupied_bands) == 1
    codes = [f.code for f in state.findings]
    assert "bandwidth_exceeds_band" in codes
    finding = next(f for f in state.findings if f.code == "bandwidth_exceeds_band")
    assert finding.severity == ValidationSeverity.BLOCKING


def test_compute_spectrum_state_overlap_is_warning_not_blocking() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0)
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

    state = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)

    overlap_findings = [f for f in state.findings if f.code == "spectral_overlap"]
    assert len(overlap_findings) == 1
    assert overlap_findings[0].severity == ValidationSeverity.WARNING
    assert all(f.severity != ValidationSeverity.BLOCKING for f in overlap_findings)


def test_compute_spectrum_state_idle_link_contributes_nothing() -> None:
    recording = make_recording(duration_s=1.0)
    link = make_link(
        recording.reference(),
        emissions=[
            RfEmission(recording=recording.reference(), start_offset=timedelta(seconds=100))
        ],
    )
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}

    state = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)

    assert state.occupied_bands == []
    assert state.findings == []


# --------------------------------------------------- zone_trigger (ADR-015 follow-up)


def _zone_triggered_link(recording_ref: RecordingReference, zone_id: UUID) -> DroneRfLink:
    zone_trigger = ZoneTriggerPolicy(zone_id=zone_id)
    return make_link(
        recording_ref,
        emissions=[RfEmission(recording=recording_ref, zone_trigger=zone_trigger)],
    )


def test_active_emission_at_zone_trigger_off_before_entering_zone() -> None:
    recording = make_recording()
    link = _zone_triggered_link(recording.reference(), _MID_LEG_ZONE.id)
    mission = make_mission([link], trajectory=_STRAIGHT_LEG)
    zones_by_id = {_MID_LEG_ZONE.id: _MID_LEG_ZONE}

    assert active_emission_at(mission, link, 0.0, recordings={}, zones_by_id=zones_by_id) is None


def test_active_emission_at_zone_trigger_on_inside_zone() -> None:
    recording = make_recording()
    link = _zone_triggered_link(recording.reference(), _MID_LEG_ZONE.id)
    mission = make_mission([link], trajectory=_STRAIGHT_LEG)
    zones_by_id = {_MID_LEG_ZONE.id: _MID_LEG_ZONE}

    # ~50s in is roughly the midpoint of the leg (see test_mission_evaluator.py's
    # equivalent straight-leg interpolation case) — inside _MID_LEG_ZONE.
    result = active_emission_at(mission, link, 50.0, recordings={}, zones_by_id=zones_by_id)
    assert result is not None


def test_active_emission_at_zone_trigger_unresolvable_zone_never_active() -> None:
    recording = make_recording()
    link = _zone_triggered_link(recording.reference(), uuid4())
    mission = make_mission([link], trajectory=_STRAIGHT_LEG)

    assert active_emission_at(mission, link, 50.0, recordings={}, zones_by_id={}) is None


def test_compute_spectrum_state_zone_trigger_produces_band_inside_zone() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0)
    link = _zone_triggered_link(recording.reference(), _MID_LEG_ZONE.id)
    mission = make_mission([link], trajectory=_STRAIGHT_LEG)
    version = make_scenario_version([mission], [recording.reference()], zones=[_MID_LEG_ZONE])
    recordings = {recording_key(recording.reference()): recording}

    outside = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)
    inside = compute_spectrum_state(version, at_seconds=50.0, recordings=recordings)

    assert outside.occupied_bands == []
    assert len(inside.occupied_bands) == 1


def test_compute_spectrum_state_zone_trigger_unsupported_template_is_blocking() -> None:
    unsupported_trajectory = Trajectory(
        template=MissionTemplate.RACETRACK,
        waypoints=_STRAIGHT_LEG.waypoints,
        default_speed_mps=10.0,
    )
    recording = make_recording(sample_rate_hz=2_000_000.0)
    link = _zone_triggered_link(recording.reference(), _MID_LEG_ZONE.id)
    mission = make_mission([link], trajectory=unsupported_trajectory)
    version = make_scenario_version([mission], [recording.reference()], zones=[_MID_LEG_ZONE])
    recordings = {recording_key(recording.reference()): recording}

    state = compute_spectrum_state(version, at_seconds=50.0, recordings=recordings)

    assert state.occupied_bands == []
    codes = {f.code for f in state.findings if f.severity == ValidationSeverity.BLOCKING}
    assert "zone_trigger_position_unresolvable" in codes


def test_compute_spectrum_state_carries_observed_by_receiver_id_through() -> None:
    receiver_id = uuid4()
    recording = make_recording(sample_rate_hz=2_000_000.0)
    link = make_link(recording.reference(), observed_by_receiver_id=receiver_id)
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}

    state = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)

    assert len(state.occupied_bands) == 1
    assert state.occupied_bands[0].observed_by_receiver_id == receiver_id


def test_compute_spectrum_state_observed_by_receiver_id_defaults_to_none() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}

    state = compute_spectrum_state(version, at_seconds=0.0, recordings=recordings)

    assert state.occupied_bands[0].observed_by_receiver_id is None
