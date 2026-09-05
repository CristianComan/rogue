"""Tests for the prepare/arm/start/stop/emergency-stop state machine (M7).

Dedicated emergency-stop tests from armed, running, and failed states are
required by CLAUDE.md section 10 ("emergency stop paths receive dedicated
tests") — not just a happy-path smoke test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from execution_factories import make_plan_and_recordings

from rogue.domain.run import RunEventKind, RunStatus, ScenarioRun
from rogue.execution.adapter import MockSDRAdapter
from rogue.execution.orchestrator import (
    InvalidRunTransitionError,
    arm_run,
    emergency_stop_run,
    prepare_run,
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


async def test_emergency_stop_records_error_but_still_reaches_terminal_state() -> None:
    plan, recordings = make_plan_and_recordings()
    adapter = _AlwaysRaisingAdapter(capabilities=plan.capability_profile.channels)
    run = make_run(replay_plan_id=plan.id)
    prepared = await prepare_run(run, plan, recordings, adapter)

    stopped = await emergency_stop_run(prepared, plan, adapter)

    assert stopped.status == RunStatus.EMERGENCY_STOPPED
    assert any("hardware bus fault" in e.message for e in stopped.events)
