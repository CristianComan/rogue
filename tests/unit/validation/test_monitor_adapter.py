"""Unit tests for rogue.validation.monitor_adapter.MockRfMonitorAdapter."""

from __future__ import annotations

from validation_factories import make_coherent_group_plan, make_monitor_plan

from rogue.domain.receiver import ReceiverType
from rogue.validation.monitor_adapter import MockRfMonitorAdapter


async def test_capture_is_deterministic_for_the_same_instant() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    adapter = MockRfMonitorAdapter()

    first = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)
    second = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)

    assert first.measured_center_frequency_hz == second.measured_center_frequency_hz
    assert first.measured_bandwidth_hz == second.measured_bandwidth_hz
    assert first.measured_start_offset_s == second.measured_start_offset_s


async def test_capture_at_a_different_instant_differs() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    adapter = MockRfMonitorAdapter()

    first = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)
    second = await adapter.capture(receiver, plan, window, None, at_seconds=2.0)

    assert first.measured_center_frequency_hz != second.measured_center_frequency_hz


async def test_capture_jitter_stays_within_bounds_of_the_planned_value() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    adapter = MockRfMonitorAdapter()

    measurement = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)

    assert abs(measurement.measured_center_frequency_hz - window.center_frequency_hz) < 1_000.0
    assert measurement.window_key == window.window_key
    assert measurement.receiver_id == receiver.id


async def test_force_deviation_hz_overrides_the_random_jitter() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    adapter = MockRfMonitorAdapter(force_deviation_hz={(receiver.id, window.window_key): 50_000.0})

    measurement = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)

    assert measurement.measured_center_frequency_hz == window.center_frequency_hz + 50_000.0


async def test_force_underrun_marks_the_measurement() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    adapter = MockRfMonitorAdapter(force_underrun={(receiver.id, window.window_key)})

    measurement = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)

    assert measurement.underrun_detected is True


async def test_capture_of_array_element_channel_includes_delay_and_phase() -> None:
    plan, receivers = make_coherent_group_plan(receiver_type=ReceiverType.AOA_DOA)
    receiver = receivers[0]
    window = next(
        w for w in plan.rf_windows for c in w.channels if c.array_element_receiver_id == receiver.id
    )
    channel = next(c for c in window.channels if c.array_element_receiver_id == receiver.id)
    adapter = MockRfMonitorAdapter()

    measurement = await adapter.capture(receiver, plan, window, channel, at_seconds=1.0)

    assert measurement.measured_delay_s is not None
    assert measurement.measured_phase_rad is not None


async def test_capture_of_monitor_window_has_no_delay_or_phase() -> None:
    plan, receiver = make_monitor_plan()
    window = plan.rf_windows[0]
    adapter = MockRfMonitorAdapter()

    measurement = await adapter.capture(receiver, plan, window, None, at_seconds=1.0)

    assert measurement.measured_delay_s is None
    assert measurement.measured_phase_rad is None
