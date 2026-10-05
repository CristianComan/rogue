"""AIR-T 7311 / AIR-T 7201 playback backend (CLAUDE.md build-order item 5)
— "identical flow" per the doc, so one backend covers both. SoapySDR
(`driver=SoapyAIRT`), based on Deepwave's "Transmit with Python"
tutorial: set rate/frequency/gain, `setupStream(SOAPY_SDR_TX, ...)`,
`writeStream` loop. TX accepts numpy arrays only, so samples are
converted cf32 -> interleaved CS16 to halve the wire bandwidth, per the
doc.

Safety (CLAUDE.md rules 1/3/5, followed verbatim): `play()` with
`arm=False` is a dry run that never imports `SoapySDR` or touches a
device at all. `arm=True` prints the exact safety banner and requires a
typed "yes" before any transmit — there is no parameter or flag that
skips this.

`play_on_channels()` is the multi-channel sibling of `AIRTBackend.play()`
— transmitting the same composite on several TX channels at once (e.g.
TX0..TX3 of an AIR7311, for a direct TX->RX cable loopback check). A
direct cable has ~0 dB path loss, unlike over-the-air use, so it also
takes `tx_attenuation_db`: extra software headroom subtracted from
`gain_db` before it reaches the device, independent of (and in addition
to) any hardware inline attenuator.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from sigmf import SigMFFile
from sigmf.sigmffile import fromfile

SAFETY_BANNER = (
    "Conducted or shielded setup only. Radiated emission requires spectrum/range authorisation."
)
DEFAULT_RAM_BUDGET_GB = 4.0
_CHUNK_SAMPLES = 1 << 20
_BYTES_PER_SAMPLE_CF32 = 8


class SoapyDeviceSeam(Protocol):
    """The minimal seam `AIRTBackend` needs — real SoapySDR behind
    `_open_real_soapy_device`, a fake in tests."""

    def set_master_clock_rate(self, rate_hz: float) -> None: ...
    def configure(
        self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
    ) -> None: ...
    def write(self, channel: int, iq_cs16_interleaved: NDArray[np.int16]) -> None: ...
    def close(self, channel: int) -> None: ...


def _open_real_soapy_device(device_args: str) -> SoapyDeviceSeam:
    """The one function that touches real SoapySDR — imported lazily so
    `AIRTBackend` stays importable/testable without it installed.
    """
    import SoapySDR  # noqa: PLC0415 - intentionally lazy, see module docstring
    from SoapySDR import SOAPY_SDR_CS16, SOAPY_SDR_TX

    device = SoapySDR.Device(device_args)
    streams: dict[int, object] = {}

    class _RealSoapyDevice:
        def set_master_clock_rate(self, rate_hz: float) -> None:
            # Confirmed against real AIR7311 hardware: SoapyAIRT refuses a
            # TX setSampleRate() that doesn't match the device's current
            # master clock rate ("Requested sample rate of N MHz not
            # supported by current master clock rate! Please set the
            # master clock rate to N MHz"). Must happen before any
            # per-channel configure/stream setup -- changing it with an
            # active stream on another channel is not supported.
            if device.getMasterClockRate() != rate_hz:
                device.setMasterClockRate(rate_hz)

        def configure(
            self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
        ) -> None:
            device.setSampleRate(SOAPY_SDR_TX, channel, rate_hz)
            device.setFrequency(SOAPY_SDR_TX, channel, freq_hz)
            device.setGain(SOAPY_SDR_TX, channel, gain_db)
            stream = device.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CS16, [channel])
            device.activateStream(stream)
            streams[channel] = stream

        def write(self, channel: int, iq_cs16_interleaved: NDArray[np.int16]) -> None:
            device.writeStream(
                streams[channel], [iq_cs16_interleaved], len(iq_cs16_interleaved) // 2
            )

        def close(self, channel: int) -> None:
            stream = streams.pop(channel, None)
            if stream is not None:
                device.deactivateStream(stream)
                device.closeStream(stream)

    return _RealSoapyDevice()


def _cf32_to_cs16(samples: NDArray[np.complexfloating]) -> NDArray[np.int16]:
    clipped = np.clip(samples, -1.0, 1.0)
    interleaved = np.empty(clipped.size * 2, dtype=np.int16)
    interleaved[0::2] = (clipped.real * 32767).astype(np.int16)
    interleaved[1::2] = (clipped.imag * 32767).astype(np.int16)
    return interleaved


class AIRTBackend:
    def __init__(
        self,
        device_args: str,
        channel: int,
        *,
        device: SoapyDeviceSeam | None = None,
        ram_budget_gb: float = DEFAULT_RAM_BUDGET_GB,
        confirm: Callable[[str], str] = input,
    ) -> None:
        self._device_args = device_args
        self._channel = channel
        self._device = device
        self._ram_budget_gb = ram_budget_gb
        self._confirm = confirm

    def play(self, composite_meta: Path, gain_db: float, repeat: int, arm: bool) -> None:
        sig = fromfile(composite_meta, skip_checksum=True)
        rate_hz = sig.get_global_field("core:sample_rate")
        captures = sig.get_captures()
        freq_hz = captures[0]["core:frequency"] if captures else 0.0
        duration_s = sig.sample_count / rate_hz if rate_hz else 0.0

        print(
            f"plan: device_args={self._device_args!r} channel={self._channel} "
            f"freq_hz={freq_hz} rate_hz={rate_hz} gain_db={gain_db} repeat={repeat} "
            f"duration_s={duration_s:.3f}"
        )
        if not arm:
            print("[dry run] no radio opened, nothing transmitted. Pass --arm to transmit.")
            return

        print(SAFETY_BANNER)
        response = self._confirm("Type 'yes' to transmit: ")
        if response.strip().lower() != "yes":
            print("not confirmed; aborting, no transmit.")
            return

        device = self._device or _open_real_soapy_device(self._device_args)
        device.set_master_clock_rate(rate_hz)
        device.configure(self._channel, freq_hz=freq_hz, rate_hz=rate_hz, gain_db=gain_db)
        try:
            composite_bytes = sig.sample_count * _BYTES_PER_SAMPLE_CF32
            use_memmap = composite_bytes > self._ram_budget_gb * 1e9
            for _ in range(repeat):
                if use_memmap:
                    self._stream_chunked(device, sig)
                else:
                    device.write(self._channel, _cf32_to_cs16(np.asarray(sig.read_samples())))
        finally:
            device.close(self._channel)

    def _stream_chunked(self, device: SoapyDeviceSeam, sig: SigMFFile) -> None:
        chunks: queue.Queue[NDArray[np.int16] | None] = queue.Queue(maxsize=4)
        total: int = sig.sample_count

        def producer() -> None:
            for start in range(0, total, _CHUNK_SAMPLES):
                count = min(_CHUNK_SAMPLES, total - start)
                chunk = sig.read_samples(start_index=start, count=count)
                chunks.put(_cf32_to_cs16(np.asarray(chunk)))
            chunks.put(None)

        thread = threading.Thread(target=producer, daemon=True)
        thread.start()
        while True:
            item = chunks.get()
            if item is None:
                break
            device.write(self._channel, item)
        thread.join()


def play_on_channels(
    device_args: str,
    channels: list[int],
    composite_meta: Path,
    gain_db: float,
    repeat: int,
    arm: bool,
    *,
    tx_attenuation_db: float = 0.0,
    device: SoapyDeviceSeam | None = None,
    confirm: Callable[[str], str] = input,
) -> None:
    """Transmit the same composite on several TX channels at once.

    Opens one TX stream per channel on a single shared device handle
    (`SoapyDeviceSeam.configure` sets up and activates that channel's own
    stream — the same thing `AIRTBackend.play()` does for one channel),
    then writes to every channel from its own thread so each starts
    within a few milliseconds of the others. That's adequate for a
    bring-up/loopback check, not a claim of phase-coherent synchronized
    start (that's M11's barrier mechanism in the main ROGUE repo, a
    different problem this independent tool doesn't address).

    Always preloads the composite fully into RAM — no chunked/memmap
    streaming across multiple channels, unlike the single-channel
    `AIRTBackend.play()`; fine for the modest recordings a loopback
    check uses, but keep composites small when using this path.
    """
    sig = fromfile(composite_meta, skip_checksum=True)
    rate_hz = sig.get_global_field("core:sample_rate")
    captures = sig.get_captures()
    freq_hz = captures[0]["core:frequency"] if captures else 0.0
    duration_s = sig.sample_count / rate_hz if rate_hz else 0.0
    effective_gain_db = gain_db - tx_attenuation_db

    print(
        f"plan: device_args={device_args!r} channels={channels} freq_hz={freq_hz} "
        f"rate_hz={rate_hz} gain_db={gain_db} tx_attenuation_db={tx_attenuation_db} "
        f"(effective gain {effective_gain_db}) repeat={repeat} duration_s={duration_s:.3f}"
    )
    if not arm:
        print("[dry run] no radio opened, nothing transmitted. Pass --arm to transmit.")
        return

    print(SAFETY_BANNER)
    if confirm("Type 'yes' to transmit: ").strip().lower() != "yes":
        print("not confirmed; aborting, no transmit.")
        return

    real_device = device or _open_real_soapy_device(device_args)
    real_device.set_master_clock_rate(rate_hz)
    cs16 = _cf32_to_cs16(np.asarray(sig.read_samples()))
    for channel in channels:
        real_device.configure(channel, freq_hz=freq_hz, rate_hz=rate_hz, gain_db=effective_gain_db)

    # An exception raised inside a thread's target doesn't propagate to
    # the caller on its own -- Python just prints it and the thread
    # dies silently, which would let a failed channel go unreported
    # while the others kept transmitting. Captured here and re-raised
    # after every channel is closed, below.
    errors: dict[int, BaseException] = {}

    def _tx_channel(channel: int) -> None:
        try:
            for _ in range(repeat):
                real_device.write(channel, cs16)
        except BaseException as exc:  # noqa: BLE001 - recorded for the caller, see above
            errors[channel] = exc

    try:
        threads = [threading.Thread(target=_tx_channel, args=(channel,)) for channel in channels]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        for channel in channels:
            real_device.close(channel)

    if errors:
        raise RuntimeError(f"channel(s) failed while transmitting: {errors}") from next(
            iter(errors.values())
        )
