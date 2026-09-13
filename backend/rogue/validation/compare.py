"""Pure comparison of one independent ``RfMeasurement`` against the compiled
``ReplayPlan`` it was captured for (M14).

Mirrors ``rogue.spectrum.occupancy``/``rogue.compiler.windows``'s
pure-function shape: no I/O, no adapter calls, deterministic given its
inputs. Called once per ``rogue.validation.orchestrator.run_validation``
capture. Tolerances below are reasonable defaults for a simulated monitor,
not a calibrated instrument specification (see ADR-014).
"""

from __future__ import annotations

from rogue.compiler.models import Allocation, CompositeChannel, RfWindow
from rogue.domain.receiver import Receiver
from rogue.domain.rf_validation import RfMeasurement, RfValidationFinding
from rogue.domain.validation import ValidationSeverity

FREQUENCY_TOLERANCE_HZ = 5_000.0
BANDWIDTH_TOLERANCE_RATIO = 0.05
TIMING_TOLERANCE_S = 0.2
DELAY_TOLERANCE_S = 1e-6
PHASE_TOLERANCE_RAD = 0.05


def compare_measurement_to_plan(
    *,
    window: RfWindow | None,
    allocation: Allocation | None,
    channel: CompositeChannel | None,
    receiver: Receiver,
    measurement: RfMeasurement,
) -> list[RfValidationFinding]:
    """Compare one capture to what the plan declares for its window/channel.

    ``window``/``allocation`` are ``None`` when the receiver expected
    coverage (e.g. a window that was active when the plan was compiled) that
    no longer exists at the captured instant — that alone is a BLOCKING
    finding and no further comparison is possible. ``channel`` is only
    provided for a TDOA/AOA_DOA array-element capture (delay/phase are
    meaningless for a MONITOR capture, which observes the whole window).
    """
    path = f"$.rf_windows[?(@.window_key=='{measurement.window_key}')]"

    if window is None:
        return [
            RfValidationFinding(
                severity=ValidationSeverity.BLOCKING,
                code="window_not_found",
                message=(
                    f"receiver {receiver.id} expected window {measurement.window_key!r} to be "
                    "active at the captured instant, but the plan has no such window"
                ),
                path=path,
            )
        ]

    findings: list[RfValidationFinding] = []

    if measurement.underrun_detected:
        findings.append(
            RfValidationFinding(
                severity=ValidationSeverity.BLOCKING,
                code="underrun_detected",
                message=f"underrun/discontinuity detected in window {measurement.window_key!r}",
                path=path,
            )
        )

    frequency_deviation_hz = abs(
        measurement.measured_center_frequency_hz - window.center_frequency_hz
    )
    if frequency_deviation_hz > FREQUENCY_TOLERANCE_HZ:
        findings.append(
            RfValidationFinding(
                severity=ValidationSeverity.BLOCKING,
                code="frequency_deviation",
                message=(
                    f"measured center frequency {measurement.measured_center_frequency_hz:.1f} Hz "
                    f"deviates from planned {window.center_frequency_hz:.1f} Hz by "
                    f"{frequency_deviation_hz:.1f} Hz (tolerance {FREQUENCY_TOLERANCE_HZ:.1f} Hz)"
                ),
                path=path,
            )
        )

    bandwidth_ratio = (
        abs(measurement.measured_bandwidth_hz - window.bandwidth_hz) / window.bandwidth_hz
        if window.bandwidth_hz > 0
        else 0.0
    )
    if bandwidth_ratio > BANDWIDTH_TOLERANCE_RATIO:
        findings.append(
            RfValidationFinding(
                severity=ValidationSeverity.WARNING,
                code="bandwidth_deviation",
                message=(
                    f"measured bandwidth {measurement.measured_bandwidth_hz:.1f} Hz deviates from "
                    f"planned {window.bandwidth_hz:.1f} Hz by {bandwidth_ratio:.1%} "
                    f"(tolerance {BANDWIDTH_TOLERANCE_RATIO:.1%})"
                ),
                path=path,
            )
        )

    if allocation is not None and measurement.measured_start_offset_s is not None:
        timing_skew_s = abs(measurement.measured_start_offset_s - allocation.start_seconds)
        if timing_skew_s > TIMING_TOLERANCE_S:
            findings.append(
                RfValidationFinding(
                    severity=ValidationSeverity.WARNING,
                    code="timing_skew",
                    message=(
                        f"measured window start {measurement.measured_start_offset_s:.3f}s "
                        f"deviates from planned {allocation.start_seconds:.3f}s by "
                        f"{timing_skew_s:.3f}s (tolerance {TIMING_TOLERANCE_S:.3f}s)"
                    ),
                    path=path,
                )
            )

    if channel is not None:
        if (
            channel.delay_offset_s is not None
            and measurement.measured_delay_s is not None
            and abs(measurement.measured_delay_s - channel.delay_offset_s) > DELAY_TOLERANCE_S
        ):
            delay_deviation_s = abs(measurement.measured_delay_s - channel.delay_offset_s)
            findings.append(
                RfValidationFinding(
                    severity=ValidationSeverity.BLOCKING,
                    code="delay_deviation",
                    message=(
                        f"measured delay {measurement.measured_delay_s * 1e9:.1f} ns deviates from "
                        f"planned {channel.delay_offset_s * 1e9:.1f} ns by "
                        f"{delay_deviation_s * 1e9:.1f} ns "
                        f"(tolerance {DELAY_TOLERANCE_S * 1e9:.1f} ns)"
                    ),
                    path=path,
                )
            )
        if (
            channel.phase_offset_rad is not None
            and measurement.measured_phase_rad is not None
            and abs(measurement.measured_phase_rad - channel.phase_offset_rad) > PHASE_TOLERANCE_RAD
        ):
            phase_deviation_rad = abs(measurement.measured_phase_rad - channel.phase_offset_rad)
            findings.append(
                RfValidationFinding(
                    severity=ValidationSeverity.BLOCKING,
                    code="phase_deviation",
                    message=(
                        f"measured phase {measurement.measured_phase_rad:.3f} rad deviates from "
                        f"planned {channel.phase_offset_rad:.3f} rad by {phase_deviation_rad:.3f} "
                        f"rad (tolerance {PHASE_TOLERANCE_RAD:.3f} rad)"
                    ),
                    path=path,
                )
            )

    return findings
