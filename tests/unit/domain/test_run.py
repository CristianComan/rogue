"""Tests for ScenarioRun, RunEvent, DeviceLease (M7 domain)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rogue.domain.run import DeviceLease, RunEvent, RunEventKind, RunStatus, ScenarioRun
from rogue.domain.validation import ValidationSeverity


def make_scenario_run(**overrides: Any) -> ScenarioRun:
    kwargs: dict[str, Any] = {
        "scenario_id": uuid4(),
        "replay_plan_id": uuid4(),
        "operator": "test-operator",
    }
    kwargs.update(overrides)
    return ScenarioRun(**kwargs)


def test_scenario_run_defaults_to_created_with_no_leases_or_events() -> None:
    run = make_scenario_run()
    assert run.status == RunStatus.CREATED
    assert run.device_leases == []
    assert run.events == []


def test_scenario_run_status_can_be_set_explicitly() -> None:
    run = make_scenario_run(status=RunStatus.RUNNING)
    assert run.status == RunStatus.RUNNING


def test_device_lease_construction() -> None:
    run_id = uuid4()
    lease = DeviceLease(
        device_id="sim-1", channel_index=0, run_id=run_id, leased_at=datetime.now(UTC)
    )
    assert lease.device_id == "sim-1"
    assert lease.channel_index == 0
    assert lease.run_id == run_id


def test_run_event_defaults_to_warning_severity() -> None:
    event = RunEvent(
        at=datetime.now(UTC), sequence=1, kind=RunEventKind.RESERVED, message="reserved sim-1:0"
    )
    assert event.severity == ValidationSeverity.WARNING


def test_run_event_device_and_channel_are_optional() -> None:
    event = RunEvent(at=datetime.now(UTC), sequence=1, kind=RunEventKind.ERROR, message="run-wide")
    assert event.device_id is None
    assert event.channel_index is None


def test_run_event_sequence_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        RunEvent(at=datetime.now(UTC), sequence=-1, kind=RunEventKind.RESERVED, message="x")
