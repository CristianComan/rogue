"""Shared vendor-agnostic `SDRAdapter` implementation for streaming, real
hardware adapters (M9/M10, ADR-009/ADR-010).

`agents/common/x440_adapter.py` (UHD) and `agents/common/air7311_adapter.py`
(SoapySDR) are both thin subclasses of `StreamingSDRAdapter` that supply a
`RealDeviceSeam` implementation and a device-family label — lease
bookkeeping, the real-TX safety gate, bounded-chunk cache-file streaming,
and cancellation are identical between vendors (the actual vendor library
only shows up behind `configure_channel`/`send_chunk`/etc.), so they live
here once rather than being duplicated per adapter.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from agents.common import cache
from rogue.catalogue.sigmf import bytes_per_sample
from rogue.compiler.models import PhysicalTxChannelCapability, RfWindow
from rogue.domain.recording import IQRecording
from rogue.domain.run import DeviceLease
from rogue.execution.adapter import AdapterDeviceStatus, AdapterOperationError

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger("rogue.agent.sdr_adapter")

DEFAULT_GAIN_DB = 0.0
STREAM_CHUNK_SAMPLES = 65_536
SUPPORTED_SAMPLE_FORMAT = "cf32_le"


class RealTxNotAuthorizedError(AdapterOperationError):
    """Raised by `start()` when `settings.enable_real_tx` is not set.

    CLAUDE.md §10: "Real TX requires an explicit environment/configuration
    gate." This is a local, device-adapter-level interlock — independent of
    (and in addition to) the compiler's `SafetyPolicyOutcome.tx_authorized`,
    which stays a structural placeholder (that's a separate policy-engine
    milestone, not touched here).
    """


@dataclass(frozen=True)
class ChannelCapabilityReadback:
    """Runtime-discovered channel capability (CLAUDE.md rule 10)."""

    tunable_ranges_hz: list[tuple[float, float]]
    max_usable_bandwidth_hz: float
    max_sample_rate_hz: float


@dataclass(frozen=True)
class ChannelConfig:
    """A channel's current configuration, as read back from the device."""

    freq_hz: float
    rate_hz: float
    bandwidth_hz: float
    gain_db: float


class RealDeviceSeam(Protocol):
    """The minimal seam a streaming real-hardware adapter needs — the same
    shape for UHD (`EttusX440Adapter`) and SoapySDR
    (`DeepwaveAIR7311Adapter`); only *how* it's opened
    (`_open_real_uhd_device` / `_open_real_soapy_device`) differs between
    vendors. Sized to what `StreamingSDRAdapter` actually calls, not either
    vendor SDK's full surface, so tests substitute a fake without
    installing either.
    """

    def num_tx_channels(self) -> int: ...
    def discover_channel(self, channel: int) -> ChannelCapabilityReadback: ...
    def configure_channel(
        self, channel: int, *, freq_hz: float, rate_hz: float, bandwidth_hz: float, gain_db: float
    ) -> None: ...
    def read_channel_config(self, channel: int) -> ChannelConfig: ...
    def send_chunk(self, channel: int, samples: np.ndarray) -> None: ...
    def end_burst(self, channel: int) -> None: ...


@dataclass
class _ChannelState:
    leased: bool = False
    configured: bool = False
    armed: bool = False
    transmitting: bool = False
    start_at_seconds: float = 0.0
    recording_path: Path | None = None
    sample_rate_hz: float | None = None
    sample_format: str | None = None
    stream_task: asyncio.Task[None] | None = None


class StreamingSDRAdapter:
    """Real `SDRAdapter` implementation for one physical unit of a
    streaming-capable vendor device family, parameterized by a
    `RealDeviceSeam` and a `device_family` label.

    Scope, for both current subclasses (M9/M10, ADR-009/ADR-010):
    - One physical unit per adapter instance — multi-unit-per-adapter
      scheduling isn't modelled; each Agent owns one adapter per device.
    - Exactly one recording per physical channel — a window whose
      composite channels reference more than one recording (two
      co-located links sharing an RF window) would need real baseband
      mixing to transmit correctly, which isn't modelled; `preflight`
      rejects that case explicitly rather than transmitting something
      wrong.
    - `cf32_le` recordings only — the sample format both vendor SDKs
      stream natively as host-side complex64; other formats are rejected
      at `preflight` with a clear error rather than a silent/lossy
      conversion.
    - Streams the cached recording once through, start to EOF, then ends
      the burst — no artificial looping and no attempt to align exactly to
      the compiled window's `end_seconds` (that needs real
      clock-referenced timed commands, an L3/L4 concern per
      `sdr-architecture.md` §5, out of scope here).
    - No gain policy: `configure` uses a fixed default gain
      (`DEFAULT_GAIN_DB`) since `RfWindow`/`CompositeChannel` don't carry
      an absolute gain target yet (`gain_offset_db` is relative) —
      flagged as a follow-up.
    """

    def __init__(
        self,
        capabilities: list[PhysicalTxChannelCapability],
        cache_dir: Path,
        device: RealDeviceSeam,
        device_family: str,
        enable_real_tx: bool = False,
    ) -> None:
        self._capabilities = capabilities
        self._device_id = capabilities[0].device_id if capabilities else f"{device_family}-unknown"
        self._device_family = device_family
        self._cache_dir = cache_dir
        self._enable_real_tx = enable_real_tx
        self._device = device
        self._channels: dict[int, _ChannelState] = {}

    def _state(self, channel_index: int) -> _ChannelState:
        return self._channels.setdefault(channel_index, _ChannelState())

    async def discover(self) -> list[PhysicalTxChannelCapability]:
        count = await asyncio.to_thread(self._device.num_tx_channels)
        capabilities = []
        for channel in range(count):
            readback = await asyncio.to_thread(self._device.discover_channel, channel)
            capabilities.append(
                PhysicalTxChannelCapability(
                    device_id=self._device_id,
                    channel_index=channel,
                    device_family=self._device_family,
                    tunable_ranges_hz=readback.tunable_ranges_hz,
                    max_usable_bandwidth_hz=readback.max_usable_bandwidth_hz,
                    max_sample_rate_hz=readback.max_sample_rate_hz,
                )
            )
        return capabilities

    async def reserve(
        self, device_id: str, channel_index: int, run_id: UUID, ttl_seconds: float
    ) -> DeviceLease:
        self._state(channel_index).leased = True
        leased_at = datetime.now(UTC)
        return DeviceLease(
            device_id=device_id,
            channel_index=channel_index,
            run_id=run_id,
            leased_at=leased_at,
            expires_at=leased_at + timedelta(seconds=ttl_seconds),
        )

    async def renew(self, lease: DeviceLease, ttl_seconds: float) -> DeviceLease:
        return lease.model_copy(
            update={"expires_at": datetime.now(UTC) + timedelta(seconds=ttl_seconds)}
        )

    async def release(self, lease: DeviceLease) -> None:
        self._state(lease.channel_index).leased = False

    async def preflight(
        self, device_id: str, channel_index: int, window: RfWindow, recordings: list[IQRecording]
    ) -> None:
        if len(recordings) != 1:
            raise AdapterOperationError(
                device_id,
                channel_index,
                f"{type(self).__name__} supports exactly one recording per physical channel "
                f"in this pass; this window needs {len(recordings)}",
            )
        recording = recordings[0]
        if recording.sample_format != SUPPORTED_SAMPLE_FORMAT:
            raise AdapterOperationError(
                device_id,
                channel_index,
                f"{type(self).__name__} only supports {SUPPORTED_SAMPLE_FORMAT} recordings in "
                f"this pass; got {recording.sample_format!r}",
            )
        state = self._state(channel_index)
        state.recording_path = cache.data_path_for(self._cache_dir, recording.id, recording.version)
        state.sample_rate_hz = recording.sample_rate_hz
        state.sample_format = recording.sample_format

    async def configure(self, device_id: str, channel_index: int, window: RfWindow) -> None:
        state = self._state(channel_index)
        rate_hz = state.sample_rate_hz or window.bandwidth_hz
        await asyncio.to_thread(
            self._device.configure_channel,
            channel_index,
            freq_hz=window.center_frequency_hz,
            rate_hz=rate_hz,
            bandwidth_hz=window.bandwidth_hz,
            gain_db=DEFAULT_GAIN_DB,
        )
        state.configured = True

    async def arm(self, device_id: str, channel_index: int, start_at_seconds: float) -> None:
        self._state(channel_index).start_at_seconds = start_at_seconds
        self._state(channel_index).armed = True

    async def start(self, device_id: str, channel_index: int) -> None:
        if not self._enable_real_tx:
            raise RealTxNotAuthorizedError(
                device_id,
                channel_index,
                "ROGUE_ENABLE_REAL_TX is not set on this Agent host; refusing to key the "
                "transmitter (CLAUDE.md §10)",
            )
        state = self._state(channel_index)
        if state.recording_path is None or state.sample_format is None:
            raise AdapterOperationError(
                device_id,
                channel_index,
                "no recording was staged for this channel during preflight",
            )
        state.transmitting = True
        state.stream_task = asyncio.create_task(self._stream(channel_index, state))

    async def _stream(self, channel_index: int, state: _ChannelState) -> None:
        import numpy as np

        assert state.recording_path is not None
        assert state.sample_format is not None
        sample_bytes = bytes_per_sample(state.sample_format)
        assert sample_bytes is not None  # already validated in preflight
        chunk_bytes = STREAM_CHUNK_SAMPLES * sample_bytes
        try:
            with state.recording_path.open("rb") as f:
                while True:
                    chunk = await asyncio.to_thread(f.read, chunk_bytes)
                    if not chunk:
                        break
                    samples = np.frombuffer(chunk, dtype=np.complex64)
                    await asyncio.to_thread(self._device.send_chunk, channel_index, samples)
        finally:
            await asyncio.to_thread(self._device.end_burst, channel_index)
            state.transmitting = False

    async def _cancel_stream(self, channel_index: int) -> None:
        state = self._state(channel_index)
        task = state.stream_task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            state.stream_task = None
        state.transmitting = False
        state.armed = False

    async def stop(self, device_id: str, channel_index: int) -> None:
        await self._cancel_stream(channel_index)
        await asyncio.to_thread(self._device.end_burst, channel_index)

    async def emergency_stop(self, device_id: str, channel_index: int) -> None:
        # Deliberately swallows errors — emergency stop must always
        # succeed, matching MockSDRAdapter's contract (CLAUDE.md §10).
        with contextlib.suppress(Exception):
            await self._cancel_stream(channel_index)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._device.end_burst, channel_index)
        state = self._state(channel_index)
        state.transmitting = False
        state.armed = False

    async def status(self, device_id: str, channel_index: int) -> AdapterDeviceStatus:
        state = self._state(channel_index)
        return AdapterDeviceStatus(
            device_id=device_id,
            channel_index=channel_index,
            leased=state.leased,
            configured=state.configured,
            armed=state.armed,
            transmitting=state.transmitting,
        )
