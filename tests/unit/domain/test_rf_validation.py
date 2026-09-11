"""Tests for RfMeasurement/RfValidationReport (M14 domain) and their
attachment to ScenarioRun.validation_reports."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from rogue.domain.rf_validation import RfMeasurement, RfValidationFinding, RfValidationReport
from rogue.domain.run import ScenarioRun
from rogue.domain.validation import ValidationSeverity


def make_measurement(**overrides: object) -> RfMeasurement:
    kwargs: dict[str, object] = {
        "receiver_id": uuid4(),
        "window_key": "window-1",
        "captured_at": datetime.now(UTC),
        "measured_center_frequency_hz": 2_412_000_000.0,
        "measured_bandwidth_hz": 1_000_000.0,
    }
    kwargs.update(overrides)
    return RfMeasurement(**kwargs)


def test_measurement_defaults_have_no_delay_phase_power_and_no_underrun() -> None:
    measurement = make_measurement()
    assert measurement.measured_power_dbfs is None
    assert measurement.measured_start_offset_s is None
    assert measurement.measured_delay_s is None
    assert measurement.measured_phase_rad is None
    assert measurement.underrun_detected is False


def test_scenario_run_defaults_to_no_validation_reports() -> None:
    run = ScenarioRun(scenario_id=uuid4(), replay_plan_id=uuid4(), operator="test-operator")
    assert run.validation_reports == []


def test_scenario_run_round_trips_validation_reports_through_json() -> None:
    receiver_id = uuid4()
    run = ScenarioRun(scenario_id=uuid4(), replay_plan_id=uuid4(), operator="test-operator")
    report = RfValidationReport(
        run_id=run.id,
        receiver_id=receiver_id,
        created_at=datetime.now(UTC),
        measurements=[make_measurement(receiver_id=receiver_id)],
        findings=[
            RfValidationFinding(
                severity=ValidationSeverity.WARNING,
                code="bandwidth_deviation",
                message="bandwidth off by 10%",
                path="$.rf_windows[?(@.window_key=='window-1')]",
            )
        ],
    )
    run = run.model_copy(update={"validation_reports": [report]})

    round_tripped = ScenarioRun.model_validate_json(run.model_dump_json())

    assert len(round_tripped.validation_reports) == 1
    assert round_tripped.validation_reports[0].receiver_id == receiver_id
    assert round_tripped.validation_reports[0].findings[0].code == "bandwidth_deviation"
