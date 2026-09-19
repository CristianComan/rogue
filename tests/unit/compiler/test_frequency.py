"""Unit tests for rogue.compiler.frequency — pure functions, no DB."""

from __future__ import annotations

from datetime import timedelta

from compiler_factories import make_link, make_recording

from rogue.compiler.frequency import realize_frequency_timeline
from rogue.domain.rf import (
    FrequencySwitchingMode,
    FrequencyTransitionType,
    RfBand,
    ScriptedFrequencyChange,
)
from rogue.spectrum.occupancy import resolve_frequency_hz

# ------------------------------------------------------------------- scripted


def test_realize_scripted_starts_with_band_min_before_first_change() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(seconds=10), frequency_hz=2_450_000_000.0)
        ],
    )

    events = realize_frequency_timeline(link, duration_s=20.0)

    assert [e.at_seconds for e in events] == [0.0, 10.0]
    assert events[0].frequency_hz == link.band.freq_min_hz
    assert events[1].frequency_hz == 2_450_000_000.0


def test_realize_scripted_change_at_zero_has_no_duplicate_initial_event() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_410_000_000.0)
        ],
    )

    events = realize_frequency_timeline(link, duration_s=20.0)

    assert len(events) == 1
    assert events[0].at_seconds == 0.0
    assert events[0].frequency_hz == 2_410_000_000.0


def test_realize_scripted_propagates_authored_transition_type() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(
                at_offset=timedelta(seconds=5),
                frequency_hz=5_800_000_000.0,
                transition_type=FrequencyTransitionType.BAND_SWITCH,
            )
        ],
    )

    events = realize_frequency_timeline(link, duration_s=10.0)

    band_switch_events = [
        e for e in events if e.transition_type == FrequencyTransitionType.BAND_SWITCH
    ]
    assert len(band_switch_events) == 1
    assert band_switch_events[0].frequency_hz == 5_800_000_000.0


def test_realize_scripted_truncates_changes_beyond_duration() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        scripted_changes=[
            ScriptedFrequencyChange(at_offset=timedelta(0), frequency_hz=2_410_000_000.0),
            ScriptedFrequencyChange(at_offset=timedelta(seconds=100), frequency_hz=2_450_000_000.0),
        ],
    )

    events = realize_frequency_timeline(link, duration_s=10.0)

    assert [e.at_seconds for e in events] == [0.0]


# -------------------------------------------------------------- probabilistic


def test_realize_probabilistic_deterministic_same_seed() -> None:
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

    events_a = realize_frequency_timeline(link_a, duration_s=30.0)
    events_b = realize_frequency_timeline(link_b, duration_s=30.0)

    assert events_a
    assert [(e.at_seconds, e.frequency_hz) for e in events_a] == [
        (e.at_seconds, e.frequency_hz) for e in events_b
    ]
    assert all(e.frequency_hz in band.allowed_channels_hz for e in events_a)


def test_realize_probabilistic_agrees_with_single_point_resolution() -> None:
    """The full-horizon timeline and M5's point-query resolver must never diverge."""
    recording = make_recording()
    band = RfBand(
        freq_min_hz=2_400_000_000.0,
        freq_max_hz=2_483_500_000.0,
        allowed_channels_hz=[2_412_000_000.0, 2_437_000_000.0, 2_462_000_000.0],
    )
    link = make_link(
        recording.reference(),
        mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE,
        band=band,
        random_seed=11,
        mean_dwell_s=3.0,
    )
    duration_s = 40.0

    events = realize_frequency_timeline(link, duration_s)

    for query_at in (0.0, 5.5, 17.3, 39.9):
        expected = resolve_frequency_hz(link, at_seconds=query_at)
        assert expected.resolved
        active = [e for e in events if e.at_seconds <= query_at]
        assert active, f"no realized event at or before {query_at}"
        assert active[-1].frequency_hz == expected.frequency_hz


def test_realize_probabilistic_missing_channels_returns_empty() -> None:
    recording = make_recording()
    link = make_link(
        recording.reference(),
        mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE,
        random_seed=1,
        mean_dwell_s=2.0,
    )  # default band has no allowed_channels_hz

    assert realize_frequency_timeline(link, duration_s=10.0) == []


# ------------------------------------------------------- unresolvable modes


def test_realize_mission_triggered_returns_empty() -> None:
    recording = make_recording()
    link = make_link(recording.reference(), mode=FrequencySwitchingMode.MISSION_TRIGGERED)

    assert realize_frequency_timeline(link, duration_s=10.0) == []


def test_realize_external_state_triggered_returns_empty() -> None:
    recording = make_recording()
    link = make_link(recording.reference(), mode=FrequencySwitchingMode.EXTERNAL_STATE_TRIGGERED)

    assert realize_frequency_timeline(link, duration_s=10.0) == []
