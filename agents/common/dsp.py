"""Continuous Doppler/delay/phase DSP applied to a coherent-group channel's
streamed I/Q chunks (M12, ADR-013).

Pure and independently unit-testable — no device, cache, or NATS
dependency — matching CLAUDE.md rule 9 ("use numerically stable NCO/phase
accumulation") and section 8's "simulation first" principle: everything
here is exercised with synthetic signals in
``tests/unit/agents/test_dsp.py``, no real SDR hardware needed.

Only wired into ``agents/common/sdr_adapter_base.StreamingSDRAdapter`` for
a ``CompositeChannel`` that actually carries coherent-group fields
(``rogue.compiler.coherent_groups``, ADR-012/ADR-013) — the overwhelming
majority of channels have none of these set and take a plain pass-through
path instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import cast

import numpy as np

from rogue.compiler.models import DopplerSample


def interpolate_doppler_hz(schedule: list[DopplerSample], elapsed_seconds: float) -> float:
    """Linear interpolation of ``schedule`` at ``elapsed_seconds``, clamped
    to the schedule's own bounds (holds the first/last sample's value
    outside its span rather than extrapolating).
    """
    if not schedule:
        return 0.0
    ordered = sorted(schedule, key=lambda s: s.t_offset_seconds)
    if elapsed_seconds <= ordered[0].t_offset_seconds:
        return ordered[0].doppler_shift_hz
    if elapsed_seconds >= ordered[-1].t_offset_seconds:
        return ordered[-1].doppler_shift_hz
    for before, after in zip(ordered, ordered[1:], strict=False):
        if before.t_offset_seconds <= elapsed_seconds <= after.t_offset_seconds:
            span = after.t_offset_seconds - before.t_offset_seconds
            if span <= 0:
                return before.doppler_shift_hz
            fraction = (elapsed_seconds - before.t_offset_seconds) / span
            return before.doppler_shift_hz + fraction * (
                after.doppler_shift_hz - before.doppler_shift_hz
            )
    return ordered[-1].doppler_shift_hz  # unreachable given the bounds checks above


@dataclass
class PhaseAccumulatorNCO:
    """A numerically controlled oscillator: advances a phase accumulator
    sample-by-sample so consecutive ``generate()`` calls stay phase-
    continuous even as the requested ``doppler_shift_hz`` changes between
    calls (a naive "reset phase to 0 every chunk" approach would introduce
    an audible/measurable discontinuity at every chunk boundary — exactly
    what CLAUDE.md rule 9 calls out).
    """

    phase_rad: float = 0.0

    def generate(
        self, num_samples: int, sample_rate_hz: float, doppler_shift_hz: float
    ) -> np.ndarray:
        """The chunk's per-sample complex rotation, ``exp(j*phase[n])`` —
        multiply this elementwise into a chunk's samples to apply the
        shift. Treats ``doppler_shift_hz`` as constant across this one call
        (the caller resolves it once per chunk via
        ``interpolate_doppler_hz`` — chunks are tens of milliseconds at
        typical sample rates, far finer than the schedule's own ~1s
        granularity) but keeps the accumulator itself continuous.
        """
        if num_samples <= 0:
            return np.array([], dtype=np.complex64)
        angular_step = 2 * math.pi * doppler_shift_hz / sample_rate_hz
        phases = self.phase_rad + angular_step * np.arange(num_samples, dtype=np.float64)
        self.phase_rad = float((phases[-1] + angular_step) % (2 * math.pi))
        return np.exp(1j * phases).astype(np.complex64)


@dataclass
class FractionalDelayLine:
    """A simple linear-interpolation fractional-sample delay, holding one
    sample of history between calls so consecutive chunks stay continuous
    across the boundary.

    This is a deliberate simplification, not a full polyphase/Farrow
    filter: linear interpolation has more high-frequency droop than a
    proper sinc-based resampler, but at the sub-microsecond delays typical
    of a compact receiver array (ADR-012's ``delay_offset_s``), the
    droop is negligible relative to what a first execution-layer pass needs
    to prove — flagged here as a known, documented limitation and a future
    refinement, not a hidden gap.
    """

    _tail: complex = field(default=0j)

    def apply(self, samples: np.ndarray, delay_seconds: float, sample_rate_hz: float) -> np.ndarray:
        if samples.size == 0:
            return samples
        delay_samples = delay_seconds * sample_rate_hz
        # Only the fractional part is applied via interpolation; whole-
        # sample shifts aren't modelled in this pass (ADR-012/ADR-013's
        # delay magnitudes are sub-sample at realistic array baselines and
        # sample rates).
        fraction = delay_samples - math.floor(delay_samples)
        extended = np.concatenate(([self._tail], samples))
        self._tail = complex(samples[-1])
        delayed = (1 - fraction) * extended[1:] + fraction * extended[:-1]
        return delayed.astype(np.complex64)


@dataclass
class CoherentChannelDSPState:
    """Per-composite-channel DSP state, stashed on the streaming adapter's
    channel state (``agents/common/sdr_adapter_base.py``) — one instance
    per coherent-group ``CompositeChannel`` being streamed, so two
    composite channels sharing one physical channel (multi-recording
    mixing, ADR-013) each get independent NCO/delay state.
    """

    static_phase_rad: float
    delay_offset_s: float
    doppler_schedule: list[DopplerSample]
    nco: PhaseAccumulatorNCO = field(default_factory=PhaseAccumulatorNCO)
    delay_line: FractionalDelayLine = field(default_factory=FractionalDelayLine)
    elapsed_seconds: float = 0.0

    def process(self, samples: np.ndarray, sample_rate_hz: float) -> np.ndarray:
        """Delay first, then apply the static AOA_DOA phase offset and the
        continuous Doppler-driven NCO rotation — advances internal state
        (elapsed time, NCO phase, delay-line history) for the next call.
        """
        delayed = self.delay_line.apply(samples, self.delay_offset_s, sample_rate_hz)
        doppler_hz = interpolate_doppler_hz(self.doppler_schedule, self.elapsed_seconds)
        rotation = self.nco.generate(delayed.size, sample_rate_hz, doppler_hz)
        self.elapsed_seconds += delayed.size / sample_rate_hz
        result = (delayed * rotation * np.exp(1j * self.static_phase_rad)).astype(np.complex64)
        return cast("np.ndarray", result)
