"""Unit tests for rogue.spectrum.occupancy — pure functions, no DB."""

from __future__ import annotations

from datetime import timedelta

from spectrum_factories import (
    make_link,
    make_mission,
    make_recording,
    make_scenario_version,
    recording_key,
)

from rogue.domain.rf import FrequencySwitchingMode, RfBand, RfEmission, ScriptedFrequencyChange
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.occupancy import (
    active_emission_at,
    compute_spectrum_state,
    resolve_frequency_hz,
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
    recordings = {recording_key(recording.reference()): recording}

    assert active_emission_at(link, 4.9, recordings) is None
    assert active_emission_at(link, 5.0, recordings) is not None
    assert active_emission_at(link, 14.9, recordings) is not None
    assert active_emission_at(link, 15.0, recordings) is None


def test_active_emission_at_loop_repeats_indefinitely() -> None:
    recording = make_recording(duration_s=1.0)
    link = make_link(
        recording.reference(),
        emissions=[
            RfEmission(recording=recording.reference(), start_offset=timedelta(0), loop=True)
        ],
    )
    recordings = {recording_key(recording.reference()): recording}

    assert active_emission_at(link, 999.0, recordings) is not None


def test_active_emission_at_unknown_duration_assumed_active() -> None:
    """No duration_override and the recording isn't resolvable: conservatively active."""
    recording = make_recording()
    link = make_link(
        recording.reference(),
        emissions=[RfEmission(recording=recording.reference(), start_offset=timedelta(0))],
    )

    assert active_emission_at(link, 999.0, recordings={}) is not None


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
