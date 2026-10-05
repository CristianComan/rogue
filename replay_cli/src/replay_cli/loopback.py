"""RF loopback self-test: TX channel N -> cable -> RX channel N.

Transmits a known tone on one TX channel and checks it arrives on the
same-numbered RX channel at the expected frequency with adequate SNR.
Channels are tested one at a time, not simultaneously, so there is no
cross-channel coupling to account for when reading results.

**Direct cable loopback has ~0 dB path loss.** Unlike over-the-air use,
there is no free-space attenuation between TX and RX, so even a modest
TX gain can saturate or damage the RX front end. Fit a fixed inline
attenuator between every TX/RX pair (the same practice the main ROGUE
repo's manual-verification-guide already uses for X440-to-analyzer
loopback testing) and start at the lowest TX/RX gain settings — this
module doesn't know your hardware's safe limits and doesn't try to
guess them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

SAFETY_BANNER = (
    "Conducted loopback only — verify an inline attenuator is fitted between every "
    "TX/RX pair before transmitting. Radiated emission requires spectrum/range authorisation."
)

# +1 MHz from the tuned center: far enough from DC/LO leakage to be unambiguous.
TONE_OFFSET_HZ = 1_000_000.0
MIN_SNR_DB = 10.0
FREQ_TOLERANCE_HZ = 5_000.0


@dataclass(frozen=True)
class LoopbackResult:
    channel: int
    passed: bool
    peak_freq_hz: float
    peak_power_db: float
    noise_floor_db: float
    snr_db: float
    message: str


class LoopbackDeviceSeam(Protocol):
    """The minimal seam `run_channel_loopback` needs — real SoapySDR
    TX+RX streaming behind `open_real_soapy_loopback_device`, a fake in
    tests.
    """

    def configure_tx(
        self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
    ) -> None: ...
    def configure_rx(
        self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
    ) -> None: ...
    def transmit_and_receive(
        self, channel: int, tx_samples: NDArray[np.complex64], num_rx_samples: int
    ) -> NDArray[np.complex64]: ...


def make_test_tone(
    num_samples: int, rate_hz: float, offset_hz: float, amplitude: float = 0.5
) -> NDArray[np.complex64]:
    t = np.arange(num_samples) / rate_hz
    return (amplitude * np.exp(2j * np.pi * offset_hz * t)).astype(np.complex64)


def analyze_capture(
    samples: NDArray[np.complex64], rate_hz: float
) -> tuple[float, float, float, float]:
    """Returns ``(peak_freq_hz, peak_power_db, noise_floor_db, snr_db)``."""
    if samples.size == 0:
        return 0.0, -240.0, -240.0, 0.0

    window = np.hanning(samples.size)
    spectrum = np.fft.fftshift(np.fft.fft(samples * window))
    power_db = 20 * np.log10(np.maximum(np.abs(spectrum), 1e-12))
    freqs = np.fft.fftshift(np.fft.fftfreq(samples.size, d=1 / rate_hz))

    peak_idx = int(np.argmax(power_db))
    peak_freq_hz = float(freqs[peak_idx])
    peak_power_db = float(power_db[peak_idx])

    # Noise floor: median power away from the peak (a small guard band
    # either side, to exclude the peak's own spectral skirt).
    guard = max(1, samples.size // 200)
    mask = np.ones(samples.size, dtype=bool)
    mask[max(0, peak_idx - guard) : peak_idx + guard + 1] = False
    noise_floor_db = float(np.median(power_db[mask])) if mask.any() else float(np.min(power_db))

    return peak_freq_hz, peak_power_db, noise_floor_db, peak_power_db - noise_floor_db


def evaluate_channel(
    channel: int,
    peak_freq_hz: float,
    peak_power_db: float,
    noise_floor_db: float,
    snr_db: float,
    expected_offset_hz: float = TONE_OFFSET_HZ,
) -> LoopbackResult:
    freq_error_hz = abs(peak_freq_hz - expected_offset_hz)
    if freq_error_hz > FREQ_TOLERANCE_HZ:
        return LoopbackResult(
            channel,
            False,
            peak_freq_hz,
            peak_power_db,
            noise_floor_db,
            snr_db,
            f"tone found at {peak_freq_hz:+.0f} Hz, expected {expected_offset_hz:+.0f} Hz "
            f"(off by {freq_error_hz:.0f} Hz) — check cabling/channel mapping",
        )
    if snr_db < MIN_SNR_DB:
        return LoopbackResult(
            channel,
            False,
            peak_freq_hz,
            peak_power_db,
            noise_floor_db,
            snr_db,
            f"tone at the right frequency but SNR only {snr_db:.1f} dB "
            f"(need >= {MIN_SNR_DB:.0f} dB) — check the cable/connector, or raise gain a "
            "little (watch for RX saturation)",
        )
    return LoopbackResult(
        channel,
        True,
        peak_freq_hz,
        peak_power_db,
        noise_floor_db,
        snr_db,
        f"OK — {snr_db:.1f} dB SNR at {peak_freq_hz:+.0f} Hz",
    )


def run_channel_loopback(
    device: LoopbackDeviceSeam,
    channel: int,
    *,
    freq_hz: float,
    rate_hz: float,
    tx_gain_db: float,
    rx_gain_db: float,
    num_samples: int,
) -> LoopbackResult:
    device.configure_tx(channel, freq_hz=freq_hz, rate_hz=rate_hz, gain_db=tx_gain_db)
    device.configure_rx(channel, freq_hz=freq_hz, rate_hz=rate_hz, gain_db=rx_gain_db)
    tone = make_test_tone(num_samples, rate_hz, TONE_OFFSET_HZ)
    received = device.transmit_and_receive(channel, tone, num_samples)
    peak_freq_hz, peak_power_db, noise_floor_db, snr_db = analyze_capture(received, rate_hz)
    return evaluate_channel(channel, peak_freq_hz, peak_power_db, noise_floor_db, snr_db)


def open_real_soapy_loopback_device(device_args: str) -> LoopbackDeviceSeam:
    """The one function that touches real SoapySDR — imported lazily so
    this module stays importable/testable without it installed.

    **Unverified**: written against SoapySDR's documented Python API
    shape (`setupStream`/`activateStream`/`writeStream`/`readStream`),
    the same pattern `backends/airt.py` already uses for TX-only, now
    with an RX stream added — not exercised against a real installation
    or device in this change.
    """
    import SoapySDR  # noqa: PLC0415 - intentionally lazy, see module docstring
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX, SOAPY_SDR_TX

    device = SoapySDR.Device(device_args)

    class _RealLoopbackDevice:
        def configure_tx(
            self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
        ) -> None:
            device.setSampleRate(SOAPY_SDR_TX, channel, rate_hz)
            device.setFrequency(SOAPY_SDR_TX, channel, freq_hz)
            device.setGain(SOAPY_SDR_TX, channel, gain_db)

        def configure_rx(
            self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float
        ) -> None:
            device.setSampleRate(SOAPY_SDR_RX, channel, rate_hz)
            device.setFrequency(SOAPY_SDR_RX, channel, freq_hz)
            device.setGain(SOAPY_SDR_RX, channel, gain_db)

        def transmit_and_receive(
            self, channel: int, tx_samples: NDArray[np.complex64], num_rx_samples: int
        ) -> NDArray[np.complex64]:
            tx_stream = device.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [channel])
            rx_stream = device.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [channel])
            device.activateStream(rx_stream)
            device.activateStream(tx_stream)
            try:
                device.writeStream(tx_stream, [tx_samples], len(tx_samples))
                received: NDArray[np.complex64] = np.zeros(num_rx_samples, dtype=np.complex64)
                filled = 0
                while filled < num_rx_samples:
                    status = device.readStream(
                        rx_stream, [received[filled:]], num_rx_samples - filled, timeoutUs=1_000_000
                    )
                    if status.ret <= 0:
                        break
                    filled += status.ret
                return received
            finally:
                device.deactivateStream(tx_stream)
                device.deactivateStream(rx_stream)
                device.closeStream(tx_stream)
                device.closeStream(rx_stream)

    return _RealLoopbackDevice()
