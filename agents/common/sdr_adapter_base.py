"""Shared vendor-agnostic `SDRAdapter` implementation for streaming, real
hardware adapters (M9/M10, ADR-009/ADR-010; extended M11/M12, ADR-013).

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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from agents.common import cache
from agents.common.dsp import CoherentChannelDSPState
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
class _PerRecordingStream:
    """One `CompositeChannel`'s contribution to a physical channel's mixed
    output (M12/multi-recording, ADR-013) — a physical channel with a
    single composite channel (the overwhelmingly common case) is just the
    N=1 case of this.
    """

    recording_path: Path
    gain_linear: float
    dsp: CoherentChannelDSPState | None


@dataclass
class _ChannelState:
    leased: bool = False
    configured: bool = False
    armed: bool = False
    transmitting: bool = False
    start_at_seconds: float = 0.0
    streams: list[_PerRecordingStream] = field(default_factory=list)
    sample_rate_hz: float | None = None
    sample_format: str | None = None
    stream_task: asyncio.Task[None] | None = None
    actual_tx_start_at: datetime | None = None
    last_error: str | None = None


class StreamingSDRAdapter:
    """Real `SDRAdapter` implementation for one physical unit of a
    streaming-capable vendor device family, parameterized by a
    `RealDeviceSeam` and a `device_family` label.

    Scope, for both current subclasses (M9/M10/M11/M12, ADR-009/ADR-010/ADR-013):
    - One physical unit per adapter instance — multi-unit-per-adapter
      scheduling isn't modelled; each Agent owns one adapter per device.
    - One or more recordings per physical channel, one per `RfWindow`
      composite channel (ADR-013 relaxes ADR-009's original one-recording
      restriction): each stream is independently gain-scaled
      (`CompositeChannel.gain_offset_db`) and, if it belongs to a coherent
      group (ADR-012), independently DSP-processed (`agents/common/dsp.py`
      — continuous Doppler-driven phase + a fractional-sample delay)
      before every stream's chunk is summed into the channel's single
      transmitted signal. A shorter recording contributes silence
      (zero-padding) once exhausted while longer ones keep streaming — no
      looping, matching the original single-recording behavior. Every
      recording mixed onto one channel must share the same sample rate;
      mismatched rates are rejected at `preflight` (no resampling is
      attempted).
    - `cf32_le` recordings only — the sample format both vendor SDKs
      stream natively as host-side complex64; other formats are rejected
      at `preflight` with a clear error rather than a silent/lossy
      conversion.
    - Streams each cached recording once through, start to EOF, then ends
      the burst once every stream in the mix is exhausted — no attempt to
      align exactly to the compiled window's `end_seconds` (that needs real
      clock-referenced timed commands, an L3/L4 concern per
      `sdr-architecture.md` §5, out of scope here).
    - `start()` accepts an optional `barrier_at` (M11, ADR-013): when given,
      the actual keying is deferred to that wall-clock instant, letting the
      control plane synchronize several channels' start across one or more
      Agents (a software barrier, L1). This call always returns as soon as
      the wait is *scheduled*, never once it fires — see `start()`'s own
      docstring for why that's a correctness requirement, not a style
      choice.
    - No gain policy beyond each recording's own `gain_offset_db`: there is
      still no absolute output-level/backoff target for the physical
      channel as a whole (`configure` uses a fixed default device gain,
      `DEFAULT_GAIN_DB`) — flagged as a follow-up, unchanged from M9.
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
        if len(recordings) < 1:
            raise AdapterOperationError(
                device_id,
                channel_index,
                f"{type(self).__name__} needs at least one recording for this channel",
            )
        for recording in recordings:
            if recording.sample_format != SUPPORTED_SAMPLE_FORMAT:
                raise AdapterOperationError(
                    device_id,
                    channel_index,
                    f"{type(self).__name__} only supports {SUPPORTED_SAMPLE_FORMAT} recordings "
                    f"in this pass; got {recording.sample_format!r}",
                )
        sample_rates = {recording.sample_rate_hz for recording in recordings}
        if len(sample_rates) > 1:
            raise AdapterOperationError(
                device_id,
                channel_index,
                f"{type(self).__name__} requires every recording mixed onto one physical "
                f"channel to share a sample rate; got {sorted(sample_rates)}",
            )

        recordings_by_ref = {
            (recording.id, recording.version): recording for recording in recordings
        }
        streams: list[_PerRecordingStream] = []
        for composite in window.channels:
            key = (composite.recording.recording_id, composite.recording.version)
            matched_recording = recordings_by_ref.get(key)
            if matched_recording is None:
                raise AdapterOperationError(
                    device_id,
                    channel_index,
                    f"window references recording {key[0]} v{key[1]}, which wasn't provided "
                    "to preflight",
                )
            dsp = None
            if (
                composite.delay_offset_s is not None
                or composite.phase_offset_rad is not None
                or composite.doppler_schedule is not None
            ):
                dsp = CoherentChannelDSPState(
                    static_phase_rad=composite.phase_offset_rad or 0.0,
                    delay_offset_s=composite.delay_offset_s or 0.0,
                    doppler_schedule=composite.doppler_schedule or [],
                )
            streams.append(
                _PerRecordingStream(
                    recording_path=cache.data_path_for(
                        self._cache_dir, matched_recording.id, matched_recording.version
                    ),
                    gain_linear=10 ** (composite.gain_offset_db / 20),
                    dsp=dsp,
                )
            )
        if not streams:
            raise AdapterOperationError(
                device_id, channel_index, "window has no composite channels to stream"
            )

        state = self._state(channel_index)
        state.streams = streams
        state.sample_rate_hz = next(iter(sample_rates))
        state.sample_format = SUPPORTED_SAMPLE_FORMAT

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

    async def start(
        self, device_id: str, channel_index: int, barrier_at: datetime | None = None
    ) -> None:
        if not self._enable_real_tx:
            raise RealTxNotAuthorizedError(
                device_id,
                channel_index,
                "ROGUE_ENABLE_REAL_TX is not set on this Agent host; refusing to key the "
                "transmitter (CLAUDE.md §10)",
            )
        state = self._state(channel_index)
        if not state.streams or state.sample_format is None:
            raise AdapterOperationError(
                device_id,
                channel_index,
                "no recording was staged for this channel during preflight",
            )
        state.last_error = None
        # This must return once the keying is *scheduled*, not once it
        # fires (M11, ADR-013): a real Agent's command loop
        # (agents/common/agent.py) handles one NATS message at a time, so a
        # synchronous wait here would desynchronize two channels owned by
        # the same Agent in a barrier group — the second wouldn't even
        # begin its own wait until the first's had already elapsed.
        state.stream_task = asyncio.create_task(
            self._run_stream(device_id, channel_index, state, barrier_at)
        )

    async def _run_stream(
        self, device_id: str, channel_index: int, state: _ChannelState, barrier_at: datetime | None
    ) -> None:
        if barrier_at is not None:
            delay = (barrier_at - datetime.now(UTC)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
        state.transmitting = True
        state.actual_tx_start_at = datetime.now(UTC)
        try:
            await self._stream(channel_index, state)
        except Exception as exc:  # noqa: BLE001 - recorded for the orchestrator to observe via status()
            state.last_error = str(exc)
            raise

    async def _stream(self, channel_index: int, state: _ChannelState) -> None:
        import numpy as np

        assert state.streams
        assert state.sample_format is not None
        sample_rate_hz = state.sample_rate_hz
        assert sample_rate_hz is not None
        sample_bytes = bytes_per_sample(state.sample_format)
        assert sample_bytes is not None  # already validated in preflight
        chunk_bytes = STREAM_CHUNK_SAMPLES * sample_bytes

        files = [stream.recording_path.open("rb") for stream in state.streams]
        try:
            while True:
                processed: list[np.ndarray] = []
                max_len = 0
                for stream, f in zip(state.streams, files, strict=True):
                    raw = await asyncio.to_thread(f.read, chunk_bytes)
                    samples = np.frombuffer(raw, dtype=np.complex64) * stream.gain_linear
                    if stream.dsp is not None:
                        samples = stream.dsp.process(samples, sample_rate_hz)
                    processed.append(samples)
                    max_len = max(max_len, samples.size)
                if max_len == 0:
                    break
                combined = np.zeros(max_len, dtype=np.complex64)
                for samples in processed:
                    combined[: samples.size] += samples
                await asyncio.to_thread(self._device.send_chunk, channel_index, combined)
        finally:
            for f in files:
                f.close()
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
        state.actual_tx_start_at = None

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
        state.actual_tx_start_at = None

    async def status(self, device_id: str, channel_index: int) -> AdapterDeviceStatus:
        state = self._state(channel_index)
        return AdapterDeviceStatus(
            device_id=device_id,
            channel_index=channel_index,
            leased=state.leased,
            configured=state.configured,
            armed=state.armed,
            transmitting=state.transmitting,
            actual_tx_start_at=state.actual_tx_start_at,
            last_error=state.last_error,
        )
