"""Tests for MockSDRAdapter (M7) — the first-class simulated SDRAdapter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
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

    lease = await adapter.reserve(DEVICE, CHANNEL, run_id, ttl_seconds=30.0)

    assert lease.device_id == DEVICE
    assert lease.channel_index == CHANNEL
    assert lease.run_id == run_id
    assert lease.expires_at > lease.leased_at
    status = await adapter.status(DEVICE, CHANNEL)
    assert status.leased is True


async def test_release_clears_the_lease() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    lease = await adapter.reserve(DEVICE, CHANNEL, uuid4(), ttl_seconds=30.0)

    await adapter.release(lease)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.leased is False


async def test_renew_extends_expiry() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    lease = await adapter.reserve(DEVICE, CHANNEL, uuid4(), ttl_seconds=30.0)

    renewed = await adapter.renew(lease, ttl_seconds=30.0)

    assert renewed.expires_at > lease.expires_at
    assert renewed.id == lease.id
    assert renewed.device_id == lease.device_id


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


async def test_start_without_barrier_at_is_unchanged_from_before_m11() -> None:
    """Regression: the default (no synchronization requested) path must
    behave exactly as it did before `barrier_at` existed.
    """
    adapter = MockSDRAdapter(capabilities=[])
    await adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)

    await adapter.start(DEVICE, CHANNEL)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.transmitting is True
    assert status.actual_tx_start_at is not None
    assert status.last_error is None


async def test_barrier_start_does_not_transmit_before_the_target_time() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    barrier_at = datetime.now(UTC) + timedelta(seconds=0.2)

    await adapter.start(DEVICE, CHANNEL, barrier_at=barrier_at)

    # start() must return once scheduled, not once the barrier fires.
    status = await adapter.status(DEVICE, CHANNEL)
    assert status.transmitting is False
    assert status.actual_tx_start_at is None


async def test_barrier_start_transmits_once_the_target_time_arrives() -> None:
    adapter = MockSDRAdapter(capabilities=[])
    barrier_at = datetime.now(UTC) + timedelta(seconds=0.05)

    await adapter.start(DEVICE, CHANNEL, barrier_at=barrier_at)
    await asyncio.sleep(0.15)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.transmitting is True
    assert status.actual_tx_start_at is not None
    assert status.actual_tx_start_at >= barrier_at


async def test_barrier_start_failure_is_reported_via_status_not_raised() -> None:
    """A barrier-scheduled start must return immediately once scheduled
    (see StreamingSDRAdapter.start's docstring for why) — a failure that
    happens once the barrier fires can't be raised back to the original
    caller, so it surfaces via status().last_error instead.
    """
    adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "start")})
    barrier_at = datetime.now(UTC) + timedelta(seconds=0.05)

    await adapter.start(DEVICE, CHANNEL, barrier_at=barrier_at)  # does not raise
    await asyncio.sleep(0.15)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.transmitting is False
    assert status.last_error is not None


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

    lease = await adapter.reserve(DEVICE, CHANNEL, uuid4(), ttl_seconds=30.0)
    assert lease.device_id == DEVICE


async def test_emergency_stop_always_succeeds_even_when_fail_on_targets_it() -> None:
    adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "emergency_stop")})
    await adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
    await adapter.start(DEVICE, CHANNEL)

    await adapter.emergency_stop(DEVICE, CHANNEL)

    status = await adapter.status(DEVICE, CHANNEL)
    assert status.transmitting is False
    assert status.armed is False
