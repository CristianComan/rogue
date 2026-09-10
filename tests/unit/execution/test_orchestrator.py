"""Tests for the prepare/arm/start/stop/emergency-stop state machine (M7).

Dedicated emergency-stop tests from armed, running, and failed states are
required by CLAUDE.md section 10 ("emergency stop paths receive dedicated
tests") — not just a happy-path smoke test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from execution_factories import make_plan_and_recordings, make_plan_and_recordings_two_channels

from rogue.domain.rf import TimingSyncClass
from rogue.domain.run import RunEventKind, RunStatus, ScenarioRun
from rogue.execution.adapter import MockSDRAdapter
from rogue.execution.orchestrator import (
    InvalidRunTransitionError,
    arm_run,
    emergency_stop_run,
    prepare_run,
    renew_leases,
    start_run,
    stop_run,
)


def make_run(**overrides: object) -> ScenarioRun:
    kwargs: dict[str, object] = {
        "scenario_id": uuid4(),
        "replay_plan_id": uuid4(),
        "operator": "test-operator",
    }
    kwargs.update(overrides)
    return ScenarioRun(**kwargs)


async def test_prepare_run_happy_path_reserves_and_configures_then_advances() -> None:
    plan, recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    prepared = await prepare_run(run, plan, recordings, adapter)

    assert prepared.status == RunStatus.PREPARED
    assert len(prepared.device_leases) == len(plan.allocations)
    kinds = [e.kind for e in prepared.events]
    assert RunEventKind.RESERVED in kinds
    assert RunEventKind.PREFETCH_VERIFIED in kinds
    assert RunEventKind.CONFIGURED in kinds


class _PreflightSpyAdapter(MockSDRAdapter):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.preflight_calls: dict[tuple[str, int], list[str]] = {}

    async def preflight(self, device_id, channel_index, window, recordings) -> None:  # type: ignore[no-untyped-def]
        self.preflight_calls[(device_id, channel_index)] = [str(r.id) for r in recordings]
        await super().preflight(device_id, channel_index, window, recordings)


async def test_prepare_run_only_preflights_each_channels_own_recording() -> None:
    plan, recordings = make_plan_and_recordings_two_channels()
    run = make_run(replay_plan_id=plan.id)
    adapter = _PreflightSpyAdapter(capabilities=plan.capability_profile.channels)

    prepared = await prepare_run(run, plan, recordings, adapter)

    assert prepared.status == RunStatus.PREPARED
    assert len(adapter.preflight_calls) == 2
    for channel_key, seen_ids in adapter.preflight_calls.items():
        assert len(seen_ids) == 1, f"{channel_key} should only see its own recording"
    seen_across_channels = {rid for ids in adapter.preflight_calls.values() for rid in ids}
    assert seen_across_channels == {str(r.id) for r in recordings.values()}


async def test_prepare_run_requires_created_status() -> None:
    plan, recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id, status=RunStatus.PREPARED)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    with pytest.raises(InvalidRunTransitionError):
        await prepare_run(run, plan, recordings, adapter)


async def test_prepare_run_fails_when_recording_is_missing_from_catalogue() -> None:
    plan, _recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    result = await prepare_run(run, plan, {}, adapter)

    assert result.status == RunStatus.FAILED
    assert result.events[-1].kind == RunEventKind.ERROR


async def test_prepare_run_fails_when_recording_hash_no_longer_matches() -> None:
    plan, recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    key, recording = next(iter(recordings.items()))
    tampered = {key: recording.model_copy(update={"sha256_data": "b" * 64})}

    result = await prepare_run(run, plan, tampered, adapter)

    assert result.status == RunStatus.FAILED
    assert "checksums" in result.events[-1].message


async def test_prepare_run_fails_on_simulated_device_failure() -> None:
    plan, recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id)
    allocation = plan.allocations[0]
    adapter = MockSDRAdapter(
        capabilities=plan.capability_profile.channels,
        fail_on={(allocation.device_id, allocation.channel_index, "reserve")},
    )

    result = await prepare_run(run, plan, recordings, adapter)

    assert result.status == RunStatus.FAILED


async def test_arm_run_happy_path() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)

    armed = await arm_run(prepared, plan, adapter)

    assert armed.status == RunStatus.ARMED
    assert armed.events[-1].kind == RunEventKind.ARMED


async def test_arm_run_requires_prepared_status() -> None:
    plan, _recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id, status=RunStatus.CREATED)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    with pytest.raises(InvalidRunTransitionError):
        await arm_run(run, plan, adapter)


async def test_start_run_happy_path() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    started = await start_run(armed, plan, adapter)

    assert started.status == RunStatus.RUNNING
    assert started.events[-1].kind == RunEventKind.STARTED


async def test_start_run_requires_armed_status() -> None:
    plan, _recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id, status=RunStatus.PREPARED)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    with pytest.raises(InvalidRunTransitionError):
        await start_run(run, plan, adapter)


# --- synchronized barrier start (M11, ADR-013) ------------------------------


async def test_start_run_defaults_to_l0_and_records_no_sync_event() -> None:
    plan, recordings = make_plan_and_recordings()
    assert plan.required_sync_class == TimingSyncClass.L0_SIMULATED
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    started = await start_run(armed, plan, adapter)

    assert started.status == RunStatus.RUNNING
    assert RunEventKind.SYNC_MEASURED not in {e.kind for e in started.events}


class _BarrierSpyAdapter(MockSDRAdapter):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.barrier_ats: dict[tuple[str, int], object] = {}

    async def start(self, device_id, channel_index, barrier_at=None) -> None:  # type: ignore[no-untyped-def]
        self.barrier_ats[(device_id, channel_index)] = barrier_at
        await super().start(device_id, channel_index, barrier_at=barrier_at)


async def test_start_run_with_barrier_synchronizes_every_channel_to_the_same_instant() -> None:
    plan, recordings = make_plan_and_recordings_two_channels()
    plan = plan.model_copy(update={"required_sync_class": TimingSyncClass.L1_SOFTWARE_BARRIER})
    adapter = _BarrierSpyAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    started = await start_run(armed, plan, adapter)

    assert started.status == RunStatus.RUNNING
    assert len(adapter.barrier_ats) == 2
    distinct_barrier_ats = set(adapter.barrier_ats.values())
    assert len(distinct_barrier_ats) == 1
    assert None not in distinct_barrier_ats


async def test_start_run_with_barrier_records_a_sync_measured_event() -> None:
    plan, recordings = make_plan_and_recordings()
    plan = plan.model_copy(update={"required_sync_class": TimingSyncClass.L2_SCHEDULED_LOCAL})
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    started = await start_run(armed, plan, adapter)

    assert started.status == RunStatus.RUNNING
    sync_events = [e for e in started.events if e.kind == RunEventKind.SYNC_MEASURED]
    assert len(sync_events) == 1
    assert "skew" in sync_events[0].message
    assert TimingSyncClass.L2_SCHEDULED_LOCAL.value in sync_events[0].message


async def test_start_run_with_barrier_fails_the_run_if_a_channel_fails_during_the_barrier() -> None:
    plan, recordings = make_plan_and_recordings()
    plan = plan.model_copy(update={"required_sync_class": TimingSyncClass.L1_SOFTWARE_BARRIER})
    allocation = plan.allocations[0]
    adapter = MockSDRAdapter(
        capabilities=plan.capability_profile.channels,
        fail_on={(allocation.device_id, allocation.channel_index, "start")},
    )
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    started = await start_run(armed, plan, adapter)

    assert started.status == RunStatus.FAILED


async def test_stop_run_from_running() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)
    running = await start_run(armed, plan, adapter)

    stopped = await stop_run(running, plan, adapter)

    assert stopped.status == RunStatus.STOPPED


async def test_stop_run_from_armed_is_allowed() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    stopped = await stop_run(armed, plan, adapter)

    assert stopped.status == RunStatus.STOPPED


async def test_stop_run_requires_armed_or_running_status() -> None:
    plan, _recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id, status=RunStatus.PREPARED)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    with pytest.raises(InvalidRunTransitionError):
        await stop_run(run, plan, adapter)


# --- dedicated emergency-stop tests (CLAUDE.md section 10) ---


async def test_emergency_stop_from_armed_reaches_emergency_stopped() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)

    stopped = await emergency_stop_run(armed, plan, adapter)

    assert stopped.status == RunStatus.EMERGENCY_STOPPED


async def test_emergency_stop_from_running_reaches_emergency_stopped() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)
    running = await start_run(armed, plan, adapter)

    stopped = await emergency_stop_run(running, plan, adapter)

    assert stopped.status == RunStatus.EMERGENCY_STOPPED


async def test_emergency_stop_from_failed_reaches_emergency_stopped() -> None:
    plan, _recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    failed = await prepare_run(run, plan, {}, adapter)
    assert failed.status == RunStatus.FAILED

    stopped = await emergency_stop_run(failed, plan, adapter)

    assert stopped.status == RunStatus.EMERGENCY_STOPPED


class _AlwaysRaisingAdapter(MockSDRAdapter):
    async def emergency_stop(self, device_id: str, channel_index: int) -> None:
        raise RuntimeError("hardware bus fault")


# --- lease renewal (M8, ADR-008) ---


async def test_renew_leases_extends_expiry_and_records_one_event() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)
    original_expiries = {lease.id: lease.expires_at for lease in armed.device_leases}

    renewed = await renew_leases(armed, plan, adapter)

    assert renewed.status == RunStatus.ARMED
    assert renewed.events[-1].kind == RunEventKind.LEASE_RENEWED
    assert len(renewed.device_leases) == len(armed.device_leases)
    for lease in renewed.device_leases:
        assert lease.expires_at > original_expiries[lease.id]


async def test_renew_leases_works_from_running() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)
    armed = await arm_run(prepared, plan, adapter)
    running = await start_run(armed, plan, adapter)

    renewed = await renew_leases(running, plan, adapter)

    assert renewed.status == RunStatus.RUNNING


async def test_renew_leases_requires_armed_or_running_status() -> None:
    plan, _recordings = make_plan_and_recordings()
    run = make_run(replay_plan_id=plan.id, status=RunStatus.PREPARED)
    adapter = MockSDRAdapter(capabilities=plan.capability_profile.channels)

    with pytest.raises(InvalidRunTransitionError):
        await renew_leases(run, plan, adapter)


async def test_emergency_stop_records_error_but_still_reaches_terminal_state() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = _AlwaysRaisingAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)

    stopped = await emergency_stop_run(prepared, plan, adapter)

    assert stopped.status == RunStatus.EMERGENCY_STOPPED
    assert any("hardware bus fault" in e.message for e in stopped.events)
