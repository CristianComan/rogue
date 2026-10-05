"""RX waterfall monitor: continuously receive on several RX channels and
render a live time x frequency (dB) waterfall for each.

Headless by design — writes a PNG (one panel per channel) to disk,
refreshed periodically, rather than opening an interactive plot window.
The AIR-T is normally accessed over SSH with no display attached; pull
the PNG over (e.g. `scp`, or a synced folder) to view it. There's
nothing stopping an interactive matplotlib backend on a host that does
have a display — this module doesn't care how the figure gets to disk,
only `scripts/rx_monitor.py`'s use of `matplotlib.use("Agg")` forces
headless.

One independent single-channel RX stream per channel (not a true
multiplexed multi-channel SoapySDR stream), each read from its own
thread — the same design choice `backends.airt.play_on_channels` makes
for TX, for the same reason: simpler, and reuses an already-working
single-channel code shape rather than a new multi-channel stream path.
"""

from __future__ import annotations

import threading
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class RxDeviceSeam(Protocol):
    """The minimal seam the receiver loop needs — real SoapySDR behind
    `open_real_soapy_rx_device`, a fake in tests."""

    def configure(
        self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
    ) -> None: ...
    def open_stream(self, channel: int) -> object: ...
    def read(self, stream: object, buf: NDArray[np.complex64]) -> int: ...
    def close_stream(self, stream: object) -> None: ...


class ChannelWaterfall:
    """A rolling time x frequency (dB) buffer for one RX channel —
    each `push()` computes one FFT row and scrolls it in at the top,
    oldest rows falling off the bottom.
    """

    def __init__(self, fft_size: int, history: int, floor_db: float = -120.0) -> None:
        self.fft_size = fft_size
        self.history = history
        self.rows = np.full((history, fft_size), floor_db, dtype=np.float32)

    def push(self, samples: NDArray[np.complex64]) -> None:
        window = np.hanning(len(samples))
        spectrum = np.fft.fftshift(np.fft.fft(samples * window, n=self.fft_size))
        power_db = 20 * np.log10(np.maximum(np.abs(spectrum), 1e-12)).astype(np.float32)
        self.rows = np.roll(self.rows, -1, axis=0)
        self.rows[-1] = power_db


def receiver_loop(
    device: RxDeviceSeam,
    channel: int,
    *,
    freq_hz: float,
    rate_hz: float,
    gain_db: float,
    chunk_samples: int,
    waterfall: ChannelWaterfall,
    stop: threading.Event,
) -> None:
    """Runs until `stop` is set — meant to be the target of its own thread,
    one per channel (see this module's docstring for why).
    """
    device.configure(channel, freq_hz=freq_hz, rate_hz=rate_hz, gain_db=gain_db)
    stream = device.open_stream(channel)
    buf: NDArray[np.complex64] = np.zeros(chunk_samples, dtype=np.complex64)
    try:
        while not stop.is_set():
            count = device.read(stream, buf)
            if count > 0:
                waterfall.push(buf[:count])
    finally:
        device.close_stream(stream)


def open_real_soapy_rx_device(device_args: str) -> RxDeviceSeam:
    """The one function that touches real SoapySDR — imported lazily so
    this module stays importable/testable without it installed.

    **Unverified**: written against SoapySDR's documented Python API
    shape, the same `setupStream`/`activateStream`/`readStream` pattern
    `backends/airt.py` and `loopback.py` already use — not exercised
    against a real installation or device in this change.
    """
    import SoapySDR  # noqa: PLC0415 - intentionally lazy, see module docstring
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX

    device = SoapySDR.Device(device_args)

    class _RealRxDevice:
        def configure(
            self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
        ) -> None:
            device.setSampleRate(SOAPY_SDR_RX, channel, rate_hz)
            device.setFrequency(SOAPY_SDR_RX, channel, freq_hz)
            device.setGain(SOAPY_SDR_RX, channel, gain_db)

        def open_stream(self, channel: int) -> object:
            stream = device.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [channel])
            device.activateStream(stream)
            return stream

        def read(self, stream: object, buf: NDArray[np.complex64]) -> int:
            status = device.readStream(stream, [buf], len(buf), timeoutUs=1_000_000)
            return int(status.ret) if status.ret > 0 else 0

        def close_stream(self, stream: object) -> None:
            device.deactivateStream(stream)
            device.closeStream(stream)

    return _RealRxDevice()
