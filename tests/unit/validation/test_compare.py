"""Unit tests for rogue.validation.compare — pure functions, no DB, no adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from validation_factories import make_coherent_group_plan, make_monitor_plan

from rogue.domain.receiver import ReceiverType
from rogue.domain.rf_validation import RfMeasurement
from rogue.domain.validation import ValidationSeverity
from rogue.validation.compare import (
    BANDWIDTH_TOLERANCE_RATIO,
    DELAY_TOLERANCE_S,
    FREQUENCY_TOLERANCE_HZ,
    PHASE_TOLERANCE_RAD,
    TIMING_TOLERANCE_S,
    compare_measurement_to_plan,
)


def _measurement_for(window, **overrides: object) -> RfMeasurement:
    kwargs: dict[str, object] = {
        "receiver_id": uuid4(),
        "window_key": window.window_key,
        "captured_at": datetime.now(UTC),
        "measured_center_frequency_hz": window.center_frequency_hz,
        "measured_bandwidth_hz": window.bandwidth_hz,
        "measured_start_offset_s": window.start_seconds,
    }
    kwargs.update(overrides)
    return RfMeasurement(**kwargs)


def _allocation_for(plan, window):
    return next(
        a
        for a in plan.allocations
        if a.window_key == window.window_key
        and a.start_seconds == window.start_seconds
        and a.end_seconds == window.end_seconds
    )


def test_window_not_found_is_blocking_and_short_circuits() -> None:
    plan, receiver = make_monitor_plan()
    measurement = _measurement_for(plan.rf_windows[0], receiver_id=receiver.id)

    findings = compare_measurement_to_plan(
        window=None, allocation=None, channel=None, receiver=receiver, measurement=measurement
    )

    assert len(findings) == 1
    assert findings[0].code == "window_not_found"
    assert findings[0].severity == ValidationSeverity.BLOCKING


def test_exact_match_produces_no_findings() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    allocation = _allocation_for(plan, window)
    measurement = _measurement_for(window, receiver_id=receiver.id)

    findings = compare_measurement_to_plan(
        window=window,
        allocation=allocation,
        channel=None,
        receiver=receiver,
        measurement=measurement,
    )

    assert findings == []


def test_underrun_is_always_blocking() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    measurement = _measurement_for(window, receiver_id=receiver.id, underrun_detected=True)

    findings = compare_measurement_to_plan(
        window=window, allocation=None, channel=None, receiver=receiver, measurement=measurement
    )

    assert any(
        f.code == "underrun_detected" and f.severity == ValidationSeverity.BLOCKING
        for f in findings
    )


def test_frequency_within_tolerance_produces_no_finding() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    measurement = _measurement_for(
        window,
        receiver_id=receiver.id,
        measured_center_frequency_hz=window.center_frequency_hz + FREQUENCY_TOLERANCE_HZ * 0.5,
    )

    findings = compare_measurement_to_plan(
        window=window, allocation=None, channel=None, receiver=receiver, measurement=measurement
    )

    assert not any(f.code == "frequency_deviation" for f in findings)


def test_frequency_beyond_tolerance_is_blocking() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    measurement = _measurement_for(
        window,
        receiver_id=receiver.id,
        measured_center_frequency_hz=window.center_frequency_hz + FREQUENCY_TOLERANCE_HZ * 2,
    )

    findings = compare_measurement_to_plan(
        window=window, allocation=None, channel=None, receiver=receiver, measurement=measurement
    )

    finding = next(f for f in findings if f.code == "frequency_deviation")
    assert finding.severity == ValidationSeverity.BLOCKING


def test_bandwidth_beyond_tolerance_is_warning() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    measurement = _measurement_for(
        window,
        receiver_id=receiver.id,
        measured_bandwidth_hz=window.bandwidth_hz * (1 + BANDWIDTH_TOLERANCE_RATIO * 2),
    )

    findings = compare_measurement_to_plan(
        window=window, allocation=None, channel=None, receiver=receiver, measurement=measurement
    )

    finding = next(f for f in findings if f.code == "bandwidth_deviation")
    assert finding.severity == ValidationSeverity.WARNING


def test_timing_skew_beyond_tolerance_is_warning() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    allocation = _allocation_for(plan, window)
    measurement = _measurement_for(
        window,
        receiver_id=receiver.id,
        measured_start_offset_s=window.start_seconds + TIMING_TOLERANCE_S * 2,
    )

    findings = compare_measurement_to_plan(
        window=window,
        allocation=allocation,
        channel=None,
        receiver=receiver,
        measurement=measurement,
    )

    finding = next(f for f in findings if f.code == "timing_skew")
    assert finding.severity == ValidationSeverity.WARNING


def test_delay_beyond_tolerance_is_blocking_for_tdoa_element() -> None:
    plan, receivers = make_coherent_group_plan(receiver_type=ReceiverType.TDOA)
    other = next(r for r in receivers if r.element_index == 1)  # non-reference element
    window = next(
        w for w in plan.rf_windows for c in w.channels if c.array_element_receiver_id == other.id
    )
    channel = next(c for c in window.channels if c.array_element_receiver_id == other.id)
    assert channel.delay_offset_s is not None
    measurement = _measurement_for(
        window,
        receiver_id=other.id,
        measured_delay_s=channel.delay_offset_s + DELAY_TOLERANCE_S * 2,
    )

    findings = compare_measurement_to_plan(
        window=window, allocation=None, channel=channel, receiver=other, measurement=measurement
    )

    finding = next(f for f in findings if f.code == "delay_deviation")
    assert finding.severity == ValidationSeverity.BLOCKING


def test_phase_beyond_tolerance_is_blocking_for_aoa_doa_element() -> None:
    plan, receivers = make_coherent_group_plan(receiver_type=ReceiverType.AOA_DOA)
    other = next(r for r in receivers if r.element_index == 1)
    window = next(
        w for w in plan.rf_windows for c in w.channels if c.array_element_receiver_id == other.id
    )
    channel = next(c for c in window.channels if c.array_element_receiver_id == other.id)
    assert channel.phase_offset_rad is not None
    measurement = _measurement_for(
        window,
        receiver_id=other.id,
        measured_phase_rad=channel.phase_offset_rad + PHASE_TOLERANCE_RAD * 2,
    )

    findings = compare_measurement_to_plan(
        window=window, allocation=None, channel=channel, receiver=other, measurement=measurement
    )

    finding = next(f for f in findings if f.code == "phase_deviation")
    assert finding.severity == ValidationSeverity.BLOCKING
