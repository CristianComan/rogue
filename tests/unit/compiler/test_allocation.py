"""Unit tests for rogue.compiler.allocation — pure functions, no DB."""

from __future__ import annotations

from uuid import UUID, uuid4

from compiler_factories import make_capability_profile

from rogue.compiler.allocation import allocate_physical_channels
from rogue.compiler.models import (
    CompositeChannel,
    HardwareCapabilityProfile,
    PhysicalTxChannelCapability,
    RfWindow,
)
from rogue.domain.rf import RfLinkRole
from rogue.domain.validation import ValidationSeverity


def _window(
    window_key: str, start: float, end: float, center_hz: float = 2_412_000_000.0
) -> RfWindow:
    return RfWindow(
        id=uuid4(),
        window_key=window_key,
        start_seconds=start,
        end_seconds=end,
        center_frequency_hz=center_hz,
        bandwidth_hz=2_000_000.0,
        channels=[],
    )


def _coherent_window(
    window_key: str, group_id: UUID, start: float, end: float, center_hz: float = 2_412_000_000.0
) -> RfWindow:
    """A window carrying one coherent-group-tagged CompositeChannel, matching
    what windows.py's expansion step actually produces (one channel per
    per-element window)."""
    channel = CompositeChannel(
        mission_id=uuid4(),
        link_id=uuid4(),
        role=RfLinkRole.C2,
        emission_id=uuid4(),
        center_frequency_hz=center_hz,
        bandwidth_hz=2_000_000.0,
        gain_offset_db=0.0,
        recording={"recording_id": uuid4(), "version": 1, "note": None},
        coherent_group_id=group_id,
        array_element_receiver_id=uuid4(),
        delay_offset_s=0.0,
    )
    return RfWindow(
        id=uuid4(),
        window_key=window_key,
        start_seconds=start,
        end_seconds=end,
        center_frequency_hz=center_hz,
        bandwidth_hz=2_000_000.0,
        channels=[channel],
    )


def test_single_window_allocated_to_a_channel() -> None:
    profile = make_capability_profile()
    windows = [_window("w1", 0.0, 10.0)]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert findings == []
    assert len(allocations) == 1
    assert allocations[0].window_key == "w1"
    assert not allocations[0].is_migration


def test_same_window_key_keeps_same_channel_across_time() -> None:
    profile = make_capability_profile()
    windows = [_window("w1", 0.0, 10.0), _window("w1", 10.0, 20.0)]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert findings == []
    assert len(allocations) == 2
    assert (allocations[0].device_id, allocations[0].channel_index) == (
        allocations[1].device_id,
        allocations[1].channel_index,
    )
    assert not allocations[1].is_migration


def test_frequency_moving_outside_tunable_range_is_a_migration() -> None:
    profile = HardwareCapabilityProfile(
        id="split-profile",
        channels=[
            PhysicalTxChannelCapability(
                device_id="dev-a",
                channel_index=0,
                device_family="simulated_generic",
                tunable_ranges_hz=[(2_000_000_000.0, 3_000_000_000.0)],
                max_usable_bandwidth_hz=20_000_000.0,
                max_sample_rate_hz=20_000_000.0,
            ),
            PhysicalTxChannelCapability(
                device_id="dev-b",
                channel_index=0,
                device_family="simulated_generic",
                tunable_ranges_hz=[(5_000_000_000.0, 6_000_000_000.0)],
                max_usable_bandwidth_hz=20_000_000.0,
                max_sample_rate_hz=20_000_000.0,
            ),
        ],
    )
    windows = [
        _window("w1", 0.0, 10.0, center_hz=2_400_000_000.0),
        _window("w1", 10.0, 20.0, center_hz=5_500_000_000.0),
    ]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert findings == []
    assert len(allocations) == 2
    assert allocations[0].device_id == "dev-a"
    assert allocations[1].device_id == "dev-b"
    assert not allocations[0].is_migration
    assert allocations[1].is_migration


def test_two_simultaneous_windows_use_different_channels() -> None:
    profile = make_capability_profile()
    windows = [_window("w1", 0.0, 10.0, 2_400_100_000.0), _window("w2", 0.0, 10.0, 2_450_000_000.0)]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert findings == []
    assert len(allocations) == 2
    used = {(a.device_id, a.channel_index) for a in allocations}
    assert len(used) == 2


def test_more_simultaneous_windows_than_channels_is_blocking() -> None:
    profile = make_capability_profile()  # 2 channels
    windows = [_window(f"w{i}", 0.0, 10.0, 2_400_100_000.0 + i * 1_000_000.0) for i in range(3)]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert len(allocations) == 2
    codes = [f.code for f in findings]
    assert "insufficient_physical_channels" in codes
    finding = next(f for f in findings if f.code == "insufficient_physical_channels")
    assert finding.severity == ValidationSeverity.BLOCKING


def test_coherent_group_with_enough_channels_allocates_all_members_atomically() -> None:
    profile = make_capability_profile()  # 2 channels
    group_id = uuid4()
    windows = [
        _coherent_window("g1", group_id, 0.0, 10.0),
        _coherent_window("g2", group_id, 0.0, 10.0),
    ]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert findings == []
    assert len(allocations) == 2
    used = {(a.device_id, a.channel_index) for a in allocations}
    assert len(used) == 2  # two distinct physical channels, not one shared


def test_coherent_group_without_enough_channels_allocates_none_of_it() -> None:
    profile = make_capability_profile()  # 2 channels
    group_id = uuid4()
    # An unrelated independent window starts first (so it's processed and
    # claims a channel before the group is considered) and its span
    # overlaps the group's, leaving only 1 free channel for the 2-member
    # coherent group.
    windows = [
        _window("independent", 0.0, 20.0, center_hz=2_460_000_000.0),
        _coherent_window("g1", group_id, 5.0, 15.0),
        _coherent_window("g2", group_id, 5.0, 15.0),
    ]

    allocations, findings = allocate_physical_channels(windows, profile)

    # Atomic: neither coherent member is allocated (not 1-of-2), while the
    # unrelated independent window is unaffected by the group's failure.
    assert len(allocations) == 1
    assert allocations[0].window_key == "independent"
    codes = [f.code for f in findings]
    assert codes.count("insufficient_physical_channels_for_coherent_group") == 1
    finding = next(
        f for f in findings if f.code == "insufficient_physical_channels_for_coherent_group"
    )
    assert finding.severity == ValidationSeverity.BLOCKING


def test_coherent_group_members_never_share_one_physical_channel() -> None:
    # Even if allocation happened to consider the same channel for both
    # (e.g. a 1-channel profile), the group must fail atomically rather
    # than double-booking one channel for two simultaneous members.
    profile = HardwareCapabilityProfile(
        id="single-channel",
        channels=[make_capability_profile().channels[0]],
    )
    group_id = uuid4()
    windows = [
        _coherent_window("g1", group_id, 0.0, 10.0),
        _coherent_window("g2", group_id, 0.0, 10.0),
    ]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert allocations == []
    assert any(f.code == "insufficient_physical_channels_for_coherent_group" for f in findings)


def test_bandwidth_exceeding_channel_capacity_is_blocking() -> None:
    profile = make_capability_profile()  # 20 MHz max
    windows = [
        RfWindow(
            id=uuid4(),
            window_key="w1",
            start_seconds=0.0,
            end_seconds=10.0,
            center_frequency_hz=2_412_000_000.0,
            bandwidth_hz=50_000_000.0,
            channels=[],
        )
    ]

    allocations, findings = allocate_physical_channels(windows, profile)

    assert allocations == []
    assert any(f.code == "insufficient_physical_channels" for f in findings)
