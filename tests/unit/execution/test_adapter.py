"""Tests for MockSDRAdapter (M7) — the first-class simulated SDRAdapter."""

from __future__ import annotations

from uuid import uuid4

import pytest
from execution_factories import make_capability_profile

from rogue.compiler.models import RfWindow
from rogue.execution.adapter import MockSDRAdapter, SimulatedDeviceFailureError

DEVICE = "sim-1"
CHANNEL = 0


def make_window() -> RfWindow:
    return RfWindow(
        id=uuid4(),
        window_key="w1",
        start_seconds=0.0,
        end_seconds=10.0,
        center_frequency_hz=2_450_000_000.0,
        bandwidth_hz=20_000_000.0,
        channels=[],
    )


async def test_discover_returns_the_configured_capabilities() -> None:
    profile = make_capability_profile()
    adapter = MockSDRAdapter(capabilities=profile.channels)

    discovered = await adapter.discover()

    assert discovered == profile.channels


async def test_reserve_marks_the_channel_leased() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    run_id = uuid4()

    lease = await adapter.reserve(DEVICE, CHANNEL, run_id)

    assert lease.device_id == DEVICE
    assert lease.channel_index == CHANNEL
    assert lease.run_id == run_id
    status = await adapter.status(DEVICE, CHANNEL)
    assert status.leased is True


async def test_release_clears_the_lease() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    lease = await adapter.reserve(DEVICE, CHANNEL, uuid4())

    await adapter.release(lease)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.leased is False


async def test_configure_marks_the_channel_configured() -> None:
    adapter = MockSDRAdapter(capabilities=[])

    await adapter.configure(DEVICE, CHANNEL, make_window())

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.configured is True


async def test_arm_then_start_marks_the_channel_transmitting() -> None:
    adapter = MockSDRAdapter(capabilities=[])

    await adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
    status_after_arm = await adapter.status(DEVICE, CHANNEL)
    assert status_after_arm.armed is True
    assert status_after_arm.transmitting is False

    await adapter.start(DEVICE, CHANNEL)
    status_after_start = await adapter.status(DEVICE, CHANNEL)
    assert status_after_start.transmitting is True


async def test_stop_clears_armed_and_transmitting() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    await adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
    await adapter.start(DEVICE, CHANNEL)

    await adapter.stop(DEVICE, CHANNEL)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.armed is False
    assert status.transmitting is False


async def test_fail_on_raises_at_the_configured_step() -> None:
    adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "configure")})

    with pytest.raises(SimulatedDeviceFailureError):
        await adapter.configure(DEVICE, CHANNEL, make_window())


async def test_fail_on_does_not_affect_other_steps() -> None:
    adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "configure")})

    lease = await adapter.reserve(DEVICE, CHANNEL, uuid4())
    assert lease.device_id == DEVICE


async def test_emergency_stop_always_succeeds_even_when_fail_on_targets_it() -> None:
    adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "emergency_stop")})
    await adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
    await adapter.start(DEVICE, CHANNEL)

    await adapter.emergency_stop(DEVICE, CHANNEL)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.transmitting is False
    assert status.armed is False
