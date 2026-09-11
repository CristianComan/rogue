"""Unit tests for rogue.validation.orchestrator.run_validation."""

from __future__ import annotations

from uuid import uuid4

import pytest
from validation_factories import make_coherent_group_plan, make_monitor_plan, make_receiver

from rogue.domain.receiver import ReceiverType
from rogue.domain.run import RunEventKind, RunStatus, ScenarioRun
from rogue.execution.orchestrator import InvalidRunTransitionError
from rogue.validation.monitor_adapter import MockRfMonitorAdapter
from rogue.validation.orchestrator import run_validation


def make_run(**overrides: object) -> ScenarioRun:
    kwargs: dict[str, object] = {
        "scenario_id": uuid4(),
        "replay_plan_id": uuid4(),
        "operator": "test-operator",
    }
    kwargs.update(overrides)
    return ScenarioRun(**kwargs)


@pytest.mark.parametrize(
    "status", [RunStatus.CREATED, RunStatus.PREPARED, RunStatus.ARMED, RunStatus.FAILED]
)
async def test_run_validation_rejects_status_other_than_running_or_stopped(
    status: RunStatus,
) -> None:
    plan, receiver = make_monitor_plan()
    run = make_run(replay_plan_id=plan.id, status=status)
    adapter = MockRfMonitorAdapter()

    with pytest.raises(InvalidRunTransitionError):
        await run_validation(run, plan, [receiver], adapter, at_seconds=1.0)


async def test_monitor_receiver_active_window_produces_a_report() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    run = make_run(replay_plan_id=plan.id, status=RunStatus.RUNNING)
    adapter = MockRfMonitorAdapter()
    at_seconds = (window.start_seconds + window.end_seconds) / 2

    validated = await run_validation(run, plan, [receiver], adapter, at_seconds)

    assert len(validated.validation_reports) == 1
    report = validated.validation_reports[0]
    assert report.receiver_id == receiver.id
    assert report.run_id == run.id
    assert len(report.measurements) == 1
    assert report.measurements[0].window_key == window.window_key
    kinds = [e.kind for e in validated.events]
    assert kinds == [RunEventKind.VALIDATION_RECORDED]


async def test_monitor_receiver_with_nothing_active_produces_no_report() -> None:
    plan, receiver = make_monitor_plan(duration_s=5.0)
    run = make_run(replay_plan_id=plan.id, status=RunStatus.RUNNING)
    adapter = MockRfMonitorAdapter()

    validated = await run_validation(run, plan, [receiver], adapter, at_seconds=1_000.0)

    assert validated.validation_reports == []
    assert validated.events == []


async def test_validation_is_append_only_across_calls() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    run = make_run(replay_plan_id=plan.id, status=RunStatus.RUNNING)
    adapter = MockRfMonitorAdapter()
    at_seconds = (window.start_seconds + window.end_seconds) / 2

    once = await run_validation(run, plan, [receiver], adapter, at_seconds)
    twice = await run_validation(once, plan, [receiver], adapter, at_seconds)

    assert len(twice.validation_reports) == 2
    assert twice.validation_reports[0] == once.validation_reports[0]
    assert len(twice.events) == 2
    assert [e.sequence for e in twice.events] == [1, 2]


async def test_array_element_receiver_captures_only_its_own_channel() -> None:
    plan, receivers = make_coherent_group_plan(receiver_type=ReceiverType.AOA_DOA)
    run = make_run(replay_plan_id=plan.id, status=RunStatus.RUNNING)
    adapter = MockRfMonitorAdapter()
    window = plan.rf_windows[0]
    at_seconds = (window.start_seconds + window.end_seconds) / 2

    validated = await run_validation(run, plan, receivers, adapter, at_seconds)

    assert len(validated.validation_reports) == 2
    receiver_ids = {r.receiver_id for r in validated.validation_reports}
    assert receiver_ids == {r.id for r in receivers}
    for report in validated.validation_reports:
        assert len(report.measurements) == 1
        measurement = report.measurements[0]
        assert measurement.measured_delay_s is not None


async def test_array_element_receiver_without_compiled_coverage_is_blocking() -> None:
    plan, _receiver = make_monitor_plan()  # non-coherent plan
    stray = make_receiver(ReceiverType.TDOA)  # never referenced by this plan's channels
    run = make_run(replay_plan_id=plan.id, status=RunStatus.RUNNING)
    adapter = MockRfMonitorAdapter()

    validated = await run_validation(run, plan, [stray], adapter, at_seconds=1.0)

    assert len(validated.validation_reports) == 1
    report = validated.validation_reports[0]
    assert report.measurements == []
    assert report.findings[0].code == "window_not_found"
