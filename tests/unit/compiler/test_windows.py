"""Unit tests for rogue.compiler.windows — pure functions, no DB."""

from __future__ import annotations

from datetime import timedelta

from compiler_factories import (
    make_capability_profile,
    make_link,
    make_mission,
    make_recording,
    make_scenario_version,
    recording_key,
)

from rogue.compiler.windows import compute_rf_windows
from rogue.domain.rf import RfBand, RfEmission, ScriptedFrequencyChange
from rogue.domain.validation import ValidationSeverity


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
