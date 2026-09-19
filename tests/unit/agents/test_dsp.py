"""Tests for agents/common/dsp.py — pure signal processing, no hardware or
mocks needed (CLAUDE.md §8: exercised entirely with synthetic signals).
"""

from __future__ import annotations

import numpy as np
import pytest
from agents.common.dsp import (
    CoherentChannelDSPState,
    FractionalDelayLine,
    PhaseAccumulatorNCO,
    interpolate_doppler_hz,
)

from rogue.compiler.models import DopplerSample

SAMPLE_RATE_HZ = 1_000_000.0


# --- interpolate_doppler_hz --------------------------------------------------


def test_interpolate_returns_zero_for_an_empty_schedule() -> None:
    assert interpolate_doppler_hz([], 5.0) == 0.0


def test_interpolate_clamps_before_the_first_sample() -> None:
    schedule = [
        DopplerSample(t_offset_seconds=1.0, doppler_shift_hz=10.0),
        DopplerSample(t_offset_seconds=2.0, doppler_shift_hz=20.0),
    ]
    assert interpolate_doppler_hz(schedule, 0.0) == 10.0


def test_interpolate_clamps_after_the_last_sample() -> None:
    schedule = [
        DopplerSample(t_offset_seconds=1.0, doppler_shift_hz=10.0),
        DopplerSample(t_offset_seconds=2.0, doppler_shift_hz=20.0),
    ]
    assert interpolate_doppler_hz(schedule, 5.0) == 20.0


def test_interpolate_midpoint_is_linear() -> None:
    schedule = [
        DopplerSample(t_offset_seconds=0.0, doppler_shift_hz=0.0),
        DopplerSample(t_offset_seconds=10.0, doppler_shift_hz=100.0),
    ]
    assert interpolate_doppler_hz(schedule, 2.5) == 25.0


# --- PhaseAccumulatorNCO ------------------------------------------------------


def test_nco_zero_shift_produces_unit_rotation() -> None:
    nco = PhaseAccumulatorNCO()
    rotation = nco.generate(100, SAMPLE_RATE_HZ, doppler_shift_hz=0.0)
    assert np.allclose(rotation, np.ones(100, dtype=np.complex64))


def test_nco_phase_is_continuous_across_chunk_boundaries() -> None:
    """Two successive chunks at a fixed shift, taken together, must trace
    exactly the same phase ramp a single call of the combined length would
    — no discontinuity/jump at the boundary (CLAUDE.md rule 9).
    """
    nco_split = PhaseAccumulatorNCO()
    chunk_a = nco_split.generate(50, SAMPLE_RATE_HZ, doppler_shift_hz=1234.0)
    chunk_b = nco_split.generate(50, SAMPLE_RATE_HZ, doppler_shift_hz=1234.0)
    split_combined = np.concatenate([chunk_a, chunk_b])

    nco_whole = PhaseAccumulatorNCO()
    whole = nco_whole.generate(100, SAMPLE_RATE_HZ, doppler_shift_hz=1234.0)

    assert np.allclose(split_combined, whole, atol=1e-5)


def test_nco_shifts_a_tone_to_the_expected_frequency_bin() -> None:
    """A DC (constant) baseband tone, shifted by a known Doppler value,
    should show its energy at exactly that frequency after an FFT.
    """
    num_samples = 4096
    doppler_shift_hz = 5_000.0
    nco = PhaseAccumulatorNCO()
    baseband = np.ones(num_samples, dtype=np.complex64)
    rotation = nco.generate(num_samples, SAMPLE_RATE_HZ, doppler_shift_hz)
    shifted = baseband * rotation

    spectrum = np.fft.fftshift(np.fft.fft(shifted))
    freqs = np.fft.fftshift(np.fft.fftfreq(num_samples, d=1 / SAMPLE_RATE_HZ))
    peak_freq = freqs[np.argmax(np.abs(spectrum))]

    assert peak_freq == pytest.approx(doppler_shift_hz, rel=0.05)


# --- FractionalDelayLine -------------------------------------------------------


def test_zero_delay_is_identity() -> None:
    delay_line = FractionalDelayLine()
    samples = np.array([1 + 1j, 2 - 1j, 3 + 0j, -1 + 2j], dtype=np.complex64)

    result = delay_line.apply(samples, delay_seconds=0.0, sample_rate_hz=SAMPLE_RATE_HZ)

    assert np.allclose(result, samples)


def test_delayed_ramp_matches_the_expected_fractional_shift() -> None:
    """Only the fractional part of a delay is applied (see the class
    docstring — whole-sample shifts aren't modelled in this pass), so a
    0.3-sample delay on a linear ramp should read back as the ramp minus
    0.3 at every interior point.
    """
    num_samples = 2000
    fractional_delay_samples = 0.3
    ramp = np.arange(num_samples, dtype=np.float64).astype(np.complex64)
    delay_line = FractionalDelayLine()

    delayed = delay_line.apply(
        ramp,
        delay_seconds=fractional_delay_samples / SAMPLE_RATE_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
    )

    # Compare interior points (away from the zero-initialized tail at the
    # very start) since the first sample necessarily interpolates against
    # that synthetic history, not a real preceding sample.
    interior = slice(10, num_samples - 10)
    expected = ramp.real[interior] - fractional_delay_samples
    assert np.allclose(delayed.real[interior], expected, atol=1e-6)


def test_delay_line_is_continuous_across_chunk_boundaries() -> None:
    delay_line_split = FractionalDelayLine()
    ramp = np.arange(200, dtype=np.float64).astype(np.complex64)
    first = delay_line_split.apply(
        ramp[:100], delay_seconds=2.3 / SAMPLE_RATE_HZ, sample_rate_hz=SAMPLE_RATE_HZ
    )
    second = delay_line_split.apply(
        ramp[100:], delay_seconds=2.3 / SAMPLE_RATE_HZ, sample_rate_hz=SAMPLE_RATE_HZ
    )
    split_combined = np.concatenate([first, second])

    delay_line_whole = FractionalDelayLine()
    whole = delay_line_whole.apply(
        ramp, delay_seconds=2.3 / SAMPLE_RATE_HZ, sample_rate_hz=SAMPLE_RATE_HZ
    )

    assert np.allclose(split_combined, whole, atol=1e-6)


# --- CoherentChannelDSPState (integration of the pieces above) ---------------


def test_coherent_state_applies_static_phase_when_doppler_is_flat() -> None:
    state = CoherentChannelDSPState(
        static_phase_rad=np.pi / 2,
        delay_offset_s=0.0,
        doppler_schedule=[DopplerSample(t_offset_seconds=0.0, doppler_shift_hz=0.0)],
    )
    samples = np.ones(10, dtype=np.complex64)

    result = state.process(samples, SAMPLE_RATE_HZ)

    assert np.allclose(result, np.full(10, 1j, dtype=np.complex64), atol=1e-5)


def test_coherent_state_tracks_elapsed_time_across_calls() -> None:
    state = CoherentChannelDSPState(static_phase_rad=0.0, delay_offset_s=0.0, doppler_schedule=[])
    state.process(np.ones(1000, dtype=np.complex64), SAMPLE_RATE_HZ)
    assert state.elapsed_seconds == pytest.approx(1000 / SAMPLE_RATE_HZ, rel=1e-9)
