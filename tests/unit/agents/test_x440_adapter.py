"""Tests for EttusX440Adapter (M9, ADR-009) against a fake UHDDevice — no
real `uhd` package or hardware needed, matching CLAUDE.md §10's simulation
default and this pass's explicit "code now, verify later" scope.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from agents.common import cache
from agents.common.x440_adapter import (
    ChannelCapabilityReadback,
    ChannelConfig,
    EttusX440Adapter,
    RealTxNotAuthorizedError,
)

from rogue.compiler.models import CompositeChannel, PhysicalTxChannelCapability, RfWindow
from rogue.domain.recording import AccessClassification, IQRecording, RecordingReference
from rogue.domain.rf import RfLinkRole
from rogue.execution.adapter import AdapterOperationError

DEVICE_ID = "x440-1"
CHANNEL = 0


@dataclass
class _FakeUHDDevice:
    configured: dict[int, dict[str, float]] = field(default_factory=dict)
    sent_chunks: dict[int, list[bytes]] = field(default_factory=dict)
    ended_bursts: list[int] = field(default_factory=list)

    def num_tx_channels(self) -> int:
        return 8

    def discover_channel(self, channel: int) -> ChannelCapabilityReadback:
        return ChannelCapabilityReadback(
            tunable_ranges_hz=[(1e6, 6e9)], max_usable_bandwidth_hz=400e6, max_sample_rate_hz=500e6
        )

    def configure_channel(
        self, channel: int, *, freq_hz: float, rate_hz: float, bandwidth_hz: float, gain_db: float
    ) -> None:
        self.configured[channel] = {
            "freq_hz": freq_hz,
            "rate_hz": rate_hz,
            "bandwidth_hz": bandwidth_hz,
            "gain_db": gain_db,
        }

    def read_channel_config(self, channel: int) -> ChannelConfig:
        cfg = self.configured.get(channel, {})
        return ChannelConfig(
            freq_hz=cfg.get("freq_hz", 0.0),
            rate_hz=cfg.get("rate_hz", 0.0),
            bandwidth_hz=cfg.get("bandwidth_hz", 0.0),
            gain_db=cfg.get("gain_db", 0.0),
        )

    def send_chunk(self, channel: int, samples: object) -> None:
        self.sent_chunks.setdefault(channel, []).append(bytes(samples))  # type: ignore[call-overload]

    def end_burst(self, channel: int) -> None:
        self.ended_bursts.append(channel)


def make_capabilities() -> list[PhysicalTxChannelCapability]:
    return [
        PhysicalTxChannelCapability(
            device_id=DEVICE_ID,
            channel_index=CHANNEL,
            device_family="x440",
            tunable_ranges_hz=[(1e6, 6e9)],
            max_usable_bandwidth_hz=400e6,
            max_sample_rate_hz=500e6,
        )
    ]


def make_recording(**overrides: object) -> IQRecording:
    kwargs: dict[str, object] = {
        "version": 1,
        "metadata_object_key": "recordings/x440-test.sigmf-meta",
        "data_object_key": "recordings/x440-test.sigmf-data",
        "sha256_metadata": "a" * 64,
        "sha256_data": "a" * 64,
        "sample_format": "cf32_le",
        "sample_rate_hz": 1_000_000.0,
        "sample_count": 4,
        "duration_s": 0.004,
        "access_classification": AccessClassification.RESTRICTED,
    }
    kwargs.update(overrides)
    return IQRecording(**kwargs)


def make_composite_channel(
    recording_ref: RecordingReference, **overrides: object
) -> CompositeChannel:
    kwargs: dict[str, object] = {
        "mission_id": uuid4(),
        "link_id": uuid4(),
        "role": RfLinkRole.C2,
        "emission_id": uuid4(),
        "center_frequency_hz": 2_450_000_000.0,
        "bandwidth_hz": 20_000_000.0,
        "gain_offset_db": 0.0,
        "recording": recording_ref,
    }
    kwargs.update(overrides)
    return CompositeChannel(**kwargs)


def make_window(*recordings: IQRecording) -> RfWindow:
    """A window with one CompositeChannel per given recording — `preflight`
    now pairs each composite channel to its resolved recording (ADR-013),
    so a window used with `preflight` needs one for each recording passed
    there. Called with no args, this is a channel-less window (fine for
    `configure`, which never reads `window.channels`).
    """
    return RfWindow(
        id=uuid4(),
        window_key="w1",
        start_seconds=0.0,
        end_seconds=10.0,
        center_frequency_hz=2_450_000_000.0,
        bandwidth_hz=20_000_000.0,
        channels=[make_composite_channel(recording.reference()) for recording in recordings],
    )


def make_adapter(
    tmp_path: Path, *, enable_real_tx: bool = True
) -> tuple[EttusX440Adapter, _FakeUHDDevice]:
    device = _FakeUHDDevice()
    adapter = EttusX440Adapter(
        capabilities=make_capabilities(),
        cache_dir=tmp_path,
        device=device,
        enable_real_tx=enable_real_tx,
    )
    return adapter, device


def _write_cf32_samples(path: Path, count: int) -> None:
    with path.open("wb") as f:
        for i in range(count):
            f.write(struct.pack("<ff", 0.001 * i, -0.001 * i))


async def test_discover_reads_back_real_device_ranges(tmp_path: Path) -> None:
    adapter, _device = make_adapter(tmp_path)

    capabilities = await adapter.discover()

    assert len(capabilities) == 8
    assert capabilities[0].device_id == DEVICE_ID
    assert capabilities[0].max_usable_bandwidth_hz == 400e6


async def test_preflight_accepts_two_recordings_mixed_onto_one_channel(tmp_path: Path) -> None:
    """ADR-013 relaxes ADR-009's original one-recording restriction — a
    window with two composite channels (e.g. two drones sharing one
    physical channel) is now accepted, each paired to its own recording.
    """
    adapter, _device = make_adapter(tmp_path)
    recording_a, recording_b = make_recording(), make_recording()
    window = make_window(recording_a, recording_b)

    await adapter.preflight(DEVICE_ID, CHANNEL, window, [recording_a, recording_b])  # no raise


async def test_preflight_rejects_a_recording_the_window_doesnt_reference(tmp_path: Path) -> None:
    adapter, _device = make_adapter(tmp_path)
    recording = make_recording()
    other_recording = make_recording(metadata_object_key="recordings/other.sigmf-meta")
    window = make_window(recording)  # only references `recording`

    with pytest.raises(AdapterOperationError):
        await adapter.preflight(DEVICE_ID, CHANNEL, window, [other_recording])


async def test_preflight_rejects_mismatched_sample_rates_across_recordings(tmp_path: Path) -> None:
    adapter, _device = make_adapter(tmp_path)
    recording_a = make_recording(sample_rate_hz=1_000_000.0)
    recording_b = make_recording(sample_rate_hz=2_000_000.0)
    window = make_window(recording_a, recording_b)

    with pytest.raises(AdapterOperationError):
        await adapter.preflight(DEVICE_ID, CHANNEL, window, [recording_a, recording_b])


async def test_preflight_rejects_unsupported_sample_format(tmp_path: Path) -> None:
    adapter, _device = make_adapter(tmp_path)
    recording = make_recording(sample_format="ri16_le")

    with pytest.raises(AdapterOperationError):
        await adapter.preflight(DEVICE_ID, CHANNEL, make_window(), [recording])


async def test_configure_calls_device_with_window_frequency(tmp_path: Path) -> None:
    adapter, device = make_adapter(tmp_path)
    recording = make_recording()
    await adapter.preflight(DEVICE_ID, CHANNEL, make_window(recording), [recording])

    await adapter.configure(DEVICE_ID, CHANNEL, make_window(recording))

    assert device.configured[CHANNEL]["freq_hz"] == 2_450_000_000.0
    assert device.configured[CHANNEL]["rate_hz"] == recording.sample_rate_hz


async def test_start_without_enable_real_tx_raises_and_does_not_touch_device(
    tmp_path: Path,
) -> None:
    adapter, device = make_adapter(tmp_path, enable_real_tx=False)
    recording = make_recording()
    _write_cf32_samples(cache.data_path_for(tmp_path, recording.id, recording.version), 4)
    await adapter.preflight(DEVICE_ID, CHANNEL, make_window(recording), [recording])
    await adapter.configure(DEVICE_ID, CHANNEL, make_window(recording))

    with pytest.raises(RealTxNotAuthorizedError):
        await adapter.start(DEVICE_ID, CHANNEL)

    assert device.sent_chunks == {}


async def test_start_streams_the_cached_recording_in_bounded_chunks(tmp_path: Path) -> None:
    adapter, device = make_adapter(tmp_path, enable_real_tx=True)
    recording = make_recording()
    _write_cf32_samples(cache.data_path_for(tmp_path, recording.id, recording.version), 4)
    await adapter.preflight(DEVICE_ID, CHANNEL, make_window(recording), [recording])
    await adapter.configure(DEVICE_ID, CHANNEL, make_window(recording))

    await adapter.start(DEVICE_ID, CHANNEL)
    stream_task = adapter._state(CHANNEL).stream_task
    assert stream_task is not None
    await stream_task

    assert CHANNEL in device.sent_chunks
    assert CHANNEL in device.ended_bursts
    status = await adapter.status(DEVICE_ID, CHANNEL)
    assert status.transmitting is False


async def test_start_without_preflight_raises() -> None:
    adapter, _device = make_adapter(Path("/tmp"), enable_real_tx=True)

    with pytest.raises(AdapterOperationError):
        await adapter.start(DEVICE_ID, CHANNEL)


async def test_stop_cancels_an_in_flight_stream(tmp_path: Path) -> None:
    adapter, device = make_adapter(tmp_path, enable_real_tx=True)
    recording = make_recording()
    # A large file so the stream task is still running when we call stop().
    _write_cf32_samples(cache.data_path_for(tmp_path, recording.id, recording.version), 200_000)
    await adapter.preflight(DEVICE_ID, CHANNEL, make_window(recording), [recording])
    await adapter.configure(DEVICE_ID, CHANNEL, make_window(recording))
    await adapter.start(DEVICE_ID, CHANNEL)

    await adapter.stop(DEVICE_ID, CHANNEL)

    status = await adapter.status(DEVICE_ID, CHANNEL)
    assert status.transmitting is False
    assert status.armed is False
    assert CHANNEL in device.ended_bursts


async def test_emergency_stop_never_raises_even_if_device_end_burst_fails(tmp_path: Path) -> None:
    class _FailingDevice(_FakeUHDDevice):
        def end_burst(self, channel: int) -> None:
            raise RuntimeError("hardware bus fault")

    device = _FailingDevice()
    adapter = EttusX440Adapter(
        capabilities=make_capabilities(), cache_dir=tmp_path, device=device, enable_real_tx=True
    )

    await adapter.emergency_stop(DEVICE_ID, CHANNEL)

    status = await adapter.status(DEVICE_ID, CHANNEL)
    assert status.transmitting is False
    assert status.armed is False
