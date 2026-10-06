"""Tests for the loopback self-test logic against a fake device seam —
no real SoapySDR or hardware (CLAUDE.md rule 4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pytest
from numpy.typing import NDArray

from replay_cli.loopback import (
    TONE_OFFSET_HZ,
    analyze_capture,
    evaluate_channel,
    make_test_tone,
    run_channel_loopback,
)

# Not 2x TONE_OFFSET_HZ: that would put the tone exactly at Nyquist, a
# degenerate bin where FFT sign labeling is ambiguous (+/- the same
# frequency) -- an artifact of that choice, not a real production case
# (the script's own default rate is 10x its tone offset).
RATE_HZ = 4_000_000.0
NUM_SAMPLES = 65536
FREQ_HZ = 2_450_000_000.0


@dataclass
class _FakeLoopbackDevice:
    tx_configured: dict[int, dict[str, float]] = field(default_factory=dict)
    rx_configured: dict[int, dict[str, float]] = field(default_factory=dict)
    transform: Callable[[NDArray[np.complex64]], NDArray[np.complex64]] | None = None

    def configure_tx(self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float) -> None:
        self.tx_configured[channel] = {"freq_hz": freq_hz, "rate_hz": rate_hz, "gain_db": gain_db}

    def configure_rx(self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float) -> None:
        self.rx_configured[channel] = {"freq_hz": freq_hz, "rate_hz": rate_hz, "gain_db": gain_db}

    def transmit_and_receive(
        self, channel: int, tx_samples: NDArray[np.complex64], num_rx_samples: int
    ) -> NDArray[np.complex64]:
        if self.transform is not None:
            return self.transform(tx_samples)
        return tx_samples.copy()


def test_make_test_tone_lands_at_expected_frequency() -> None:
    tone = make_test_tone(NUM_SAMPLES, RATE_HZ, TONE_OFFSET_HZ)

    peak_freq_hz, _, _, snr_db = analyze_capture(tone, RATE_HZ)

    assert peak_freq_hz == pytest.approx(TONE_OFFSET_HZ, abs=50.0)
    assert snr_db > 40.0


def test_perfect_loopback_passes_and_configures_both_directions() -> None:
    device = _FakeLoopbackDevice()

    result = run_channel_loopback(
        device,
        2,
        freq_hz=FREQ_HZ,
        rate_hz=RATE_HZ,
        tx_gain_db=-5.0,
        rx_gain_db=-5.0,
        num_samples=NUM_SAMPLES,
    )

    assert result.passed
    assert result.channel == 2
    assert device.tx_configured[2] == {"freq_hz": FREQ_HZ, "rate_hz": RATE_HZ, "gain_db": -5.0}
    assert device.rx_configured[2] == {"freq_hz": FREQ_HZ, "rate_hz": RATE_HZ, "gain_db": -5.0}


def test_wrong_frequency_fails_as_a_cabling_mismatch() -> None:
    # As if the cable were plugged into a different RX channel entirely.
    def wrong_channel(tx_samples: NDArray[np.complex64]) -> NDArray[np.complex64]:
        return make_test_tone(len(tx_samples), RATE_HZ, TONE_OFFSET_HZ * 3)

    device = _FakeLoopbackDevice(transform=wrong_channel)

    result = run_channel_loopback(
        device,
        0,
        freq_hz=FREQ_HZ,
        rate_hz=RATE_HZ,
        tx_gain_db=0.0,
        rx_gain_db=0.0,
        num_samples=NUM_SAMPLES,
    )

    assert not result.passed
    assert "check cabling" in result.message


def test_low_snr_fails() -> None:
    # Exercised directly against evaluate_channel (the pass/fail decision
    # itself) rather than via a synthesized noisy capture: the FFT peak
    # search is winner-take-all, so there's no stable signal/noise mix
    # that reliably lands "right frequency, SNR just under the
    # threshold" without being sensitive to the exact noise realization
    # -- this is simpler and deterministic.
    result = evaluate_channel(
        channel=1,
        peak_freq_hz=TONE_OFFSET_HZ,
        peak_power_db=5.0,
        noise_floor_db=0.0,
        snr_db=5.0,
    )

    assert not result.passed
    assert "SNR" in result.message


def test_no_signal_received_fails() -> None:
    device = _FakeLoopbackDevice(transform=lambda tx: np.zeros_like(tx))

    result = run_channel_loopback(
        device,
        3,
        freq_hz=FREQ_HZ,
        rate_hz=RATE_HZ,
        tx_gain_db=0.0,
        rx_gain_db=0.0,
        num_samples=NUM_SAMPLES,
    )

    assert not result.passed
