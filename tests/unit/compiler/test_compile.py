"""End-to-end unit tests for rogue.compiler.compile — pure functions, no DB."""

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

from rogue.compiler.compile import COMPILER_VERSION, compile_replay_plan
from rogue.domain.rf import RfBand, ScriptedFrequencyChange
from rogue.domain.validation import ValidationSeverity


def test_compile_happy_path_produces_a_deterministic_plan() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=100.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    plan = compile_replay_plan(version, recordings, duration_s=20.0, capability_profile=profile)

    assert plan.scenario_id == version.scenario_id
    assert plan.scenario_version_number == version.version_number
    assert plan.compiler_version == COMPILER_VERSION
    assert plan.duration_s == 20.0
    assert plan.capability_profile == profile
    assert len(plan.recording_manifest) == 1
    assert plan.recording_manifest[0].recording_id == recording.id
    assert len(plan.rf_windows) == 1
    assert len(plan.allocations) == 1
    assert plan.safety_policy_outcome.tx_authorized is False
    assert all(f.severity != ValidationSeverity.BLOCKING for f in plan.findings)
    assert len(plan.realized_frequency_events) == 1


def test_compile_is_deterministic_across_calls() -> None:
    recording = make_recording(sample_rate_hz=2_000_000.0, duration_s=100.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    plan_a = compile_replay_plan(version, recordings, duration_s=20.0, capability_profile=profile)
    plan_b = compile_replay_plan(version, recordings, duration_s=20.0, capability_profile=profile)

    assert plan_a.realized_frequency_events == plan_b.realized_frequency_events
    assert [w.model_dump(exclude={"id"}) for w in plan_a.rf_windows] == [
        w.model_dump(exclude={"id"}) for w in plan_b.rf_windows
    ]
    assert plan_a.allocations == plan_b.allocations


def test_compile_infeasible_bandwidth_surfaces_blocking_finding() -> None:
    recording = make_recording(sample_rate_hz=50_000_000.0, duration_s=100.0)
    link = make_link(recording.reference())
    version = make_scenario_version([make_mission([link])], [recording.reference()])
    recordings = {recording_key(recording.reference()): recording}
    profile = make_capability_profile()

    plan = compile_replay_plan(version, recordings, duration_s=10.0, capability_profile=profile)

    assert plan.rf_windows == []
    assert plan.allocations == []
    assert any(f.severity == ValidationSeverity.BLOCKING for f in plan.findings)


def test_compile_band_switch_propagates_to_realized_events_and_allocation() -> None:
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

    plan = compile_replay_plan(version, recordings, duration_s=10.0, capability_profile=profile)

    assert len(plan.realized_frequency_events) == 2
    assert len(plan.rf_windows) == 2
    assert len(plan.allocations) == 2
