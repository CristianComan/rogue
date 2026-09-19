"""Vendor-neutral RF monitor/capture contract (M14) and its first-class
simulated implementation.

Deliberately separate from ``rogue.execution.adapter.SDRAdapter`` (the TX
command path) — no shared imports or state between the two — per CLAUDE.md
rule 15 ("independent RF validation is not the replay path") and
rf-model.md section 9. A real implementation (spectrum analyzer, RX-SDR
loopback) is out of scope for this pass, matching M9-M13's "code complete,
hardware-unverified" precedent (see ADR-014); this module only needs to
exist and be stable enough for ``rogue.validation.orchestrator`` to depend
on it.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from rogue.compiler.models import CompositeChannel, ReplayPlan, RfWindow
from rogue.domain.receiver import Receiver
from rogue.domain.rf_validation import RfMeasurement


class RfMonitorAdapter(Protocol):
    """One independent capture against a window (MONITOR) or a specific
    array-element channel within it (TDOA/AOA_DOA)."""

    async def capture(
        self,
        receiver: Receiver,
        plan: ReplayPlan,
        window: RfWindow,
        channel: CompositeChannel | None,
        at_seconds: float,
    ) -> RfMeasurement: ...


# Bounded synthetic jitter magnitudes for the simulated capture (ADR-014) —
# small enough to normally pass rogue.validation.compare's tolerances,
# large enough to be real, exercisable signal rather than a tautological
# always-pass echo of the plan's own declared values.
_FREQUENCY_JITTER_HZ = 500.0
_BANDWIDTH_JITTER_RATIO = 0.01
_TIMING_JITTER_S = 0.01
_DELAY_JITTER_S = 1e-9
_PHASE_JITTER_RAD = 0.005


class MockRfMonitorAdapter:
    """A first-class simulated ``RfMonitorAdapter`` (sdr-architecture.md
    section 8's "not a throwaway mock" precedent, applied to the
    independent validation path).

    Reads the plan's declared window/channel values as ground truth — the
    only ground truth a *simulated* capture can have — and injects a small
    deterministic bounded jitter, seeded from ``(receiver.id,
    window.window_key, at_seconds)`` so repeated captures of the same
    instant are reproducible. ``force_deviation_hz``/``force_underrun`` let
    a test push a specific ``(receiver_id, window_key)`` capture outside
    tolerance on demand, mirroring ``MockSDRAdapter.fail_on``'s precedent.
    """

    def __init__(
        self,
        *,
        force_deviation_hz: dict[tuple[UUID, str], float] | None = None,
        force_underrun: set[tuple[UUID, str]] | None = None,
    ) -> None:
        self._force_deviation_hz = force_deviation_hz or {}
        self._force_underrun = force_underrun or set()

    def _rng(self, receiver: Receiver, window: RfWindow, at_seconds: float) -> random.Random:
        return random.Random(f"{receiver.id}:{window.window_key}:{at_seconds}")

    async def capture(
        self,
        receiver: Receiver,
        plan: ReplayPlan,
        window: RfWindow,
        channel: CompositeChannel | None,
        at_seconds: float,
    ) -> RfMeasurement:
        rng = self._rng(receiver, window, at_seconds)
        key = (receiver.id, window.window_key)

        frequency_jitter_hz = self._force_deviation_hz.get(
            key, rng.uniform(-_FREQUENCY_JITTER_HZ, _FREQUENCY_JITTER_HZ)
        )
        bandwidth_jitter_ratio = rng.uniform(-_BANDWIDTH_JITTER_RATIO, _BANDWIDTH_JITTER_RATIO)
        timing_jitter_s = rng.uniform(-_TIMING_JITTER_S, _TIMING_JITTER_S)

        measured_delay_s: float | None = None
        measured_phase_rad: float | None = None
        if channel is not None:
            if channel.delay_offset_s is not None:
                measured_delay_s = channel.delay_offset_s + rng.uniform(
                    -_DELAY_JITTER_S, _DELAY_JITTER_S
                )
            if channel.phase_offset_rad is not None:
                measured_phase_rad = channel.phase_offset_rad + rng.uniform(
                    -_PHASE_JITTER_RAD, _PHASE_JITTER_RAD
                )

        return RfMeasurement(
            receiver_id=receiver.id,
            window_key=window.window_key,
            captured_at=datetime.now(UTC),
            measured_center_frequency_hz=window.center_frequency_hz + frequency_jitter_hz,
            measured_bandwidth_hz=window.bandwidth_hz * (1.0 + bandwidth_jitter_ratio),
            measured_power_dbfs=None,
            measured_start_offset_s=window.start_seconds + timing_jitter_s,
            measured_delay_s=measured_delay_s,
            measured_phase_rad=measured_phase_rad,
            underrun_detected=key in self._force_underrun,
        )
