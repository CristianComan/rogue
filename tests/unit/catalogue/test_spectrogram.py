"""Tests for STFT spectrogram computation over decoded I/Q samples."""

from __future__ import annotations

import numpy as np

from rogue.catalogue.spectrogram import compute_spectrogram, decode_iq_samples


def test_decode_cf32_le_round_trips_known_values() -> None:
    raw = np.array([1.0, -0.5, 0.25, 0.75], dtype="<f4").tobytes()
    samples = decode_iq_samples(raw, "cf32_le")
    assert samples.tolist() == [complex(1.0, -0.5), complex(0.25, 0.75)]


def test_decode_ci16_le_normalizes_by_max_magnitude() -> None:
    raw = np.array([16384, 0], dtype="<i2").tobytes()
    samples = decode_iq_samples(raw, "ci16_le")
    assert samples[0].real == 16384 / float(np.iinfo(np.dtype("<i2")).max)
    assert samples[0].imag == 0.0


def test_compute_spectrogram_peak_bin_matches_injected_tone() -> None:
    sample_rate_hz = 1_000_000.0
    tone_hz = 120_000.0
    fft_size = 512
    n_samples = fft_size * 4

    t = np.arange(n_samples) / sample_rate_hz
    tone = np.exp(2j * np.pi * tone_hz * t)

    result = compute_spectrogram(tone, sample_rate_hz, fft_size=fft_size)

    assert len(result.time_offsets_s) == 4
    assert len(result.freq_offsets_hz) == fft_size
    for time_bin in result.magnitude_db:
        peak_index = int(np.argmax(time_bin))
        peak_freq = result.freq_offsets_hz[peak_index]
        bin_width = sample_rate_hz / fft_size
        assert abs(peak_freq - tone_hz) < bin_width


def test_compute_spectrogram_empty_input_returns_empty_result() -> None:
    result = compute_spectrogram(np.array([], dtype=np.complex128), 1_000_000.0)
    assert result.time_offsets_s == []
    assert result.freq_offsets_hz == []
    assert result.magnitude_db == []


def test_compute_spectrogram_shrinks_fft_size_below_sample_count() -> None:
    samples = np.exp(2j * np.pi * 0.1 * np.arange(64))
    result = compute_spectrogram(samples, 1_000_000.0, fft_size=1024)
    assert len(result.freq_offsets_hz) == 64
