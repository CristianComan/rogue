"""Independent RF validation pass (M14), pure and DB-free — mirrors
``rogue.execution.orchestrator``'s split from ``rogue.persistence.run``:
this module takes already-loaded domain objects and a monitor adapter, and
returns an updated ``ScenarioRun``; ``rogue.persistence.run`` does the
surrounding database I/O.

Captures every ``Receiver`` relevant at one explicit scenario-time instant
(``at_seconds`` — mirrors M5's ``at_seconds``/M6's ``duration_s``
explicit-horizon precedent, not a continuous live-streaming monitor) and
appends one ``RfValidationReport`` per receiver that had something to
report. A receiver with nothing active at ``at_seconds`` (e.g. a MONITOR
receiver during a silent span) contributes no report — that is not an
error, just nothing to validate right now.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from rogue.compiler.models import Allocation, CompositeChannel, ReplayPlan, RfWindow
from rogue.domain.receiver import Receiver, ReceiverType
from rogue.domain.rf_validation import RfMeasurement, RfValidationFinding, RfValidationReport
from rogue.domain.run import RunEvent, RunEventKind, RunStatus, ScenarioRun
from rogue.domain.validation import ValidationSeverity
from rogue.execution.orchestrator import InvalidRunTransitionError
from rogue.validation.compare import compare_measurement_to_plan
from rogue.validation.monitor_adapter import RfMonitorAdapter


def _active_windows(plan: ReplayPlan, at_seconds: float) -> list[RfWindow]:
    return [w for w in plan.rf_windows if w.start_seconds <= at_seconds < w.end_seconds]


def _allocation_for(plan: ReplayPlan, window: RfWindow) -> Allocation | None:
    for allocation in plan.allocations:
        if (
            allocation.window_key == window.window_key
            and allocation.start_seconds == window.start_seconds
            and allocation.end_seconds == window.end_seconds
        ):
            return allocation
    return None


def _windows_for_array_element(
    plan: ReplayPlan, receiver_id: UUID
) -> list[tuple[RfWindow, CompositeChannel]]:
    return [
        (window, channel)
        for window in plan.rf_windows
        for channel in window.channels
        if channel.array_element_receiver_id == receiver_id
    ]


async def _validate_monitor_receiver(
    receiver: Receiver, plan: ReplayPlan, monitor_adapter: RfMonitorAdapter, at_seconds: float
) -> tuple[list[RfMeasurement], list[RfValidationFinding]]:
    measurements: list[RfMeasurement] = []
    findings: list[RfValidationFinding] = []
    for window in _active_windows(plan, at_seconds):
        allocation = _allocation_for(plan, window)
        measurement = await monitor_adapter.capture(receiver, plan, window, None, at_seconds)
        measurements.append(measurement)
        findings.extend(
            compare_measurement_to_plan(
                window=window,
                allocation=allocation,
                channel=None,
                receiver=receiver,
                measurement=measurement,
            )
        )
    return measurements, findings


async def _validate_array_element_receiver(
    receiver: Receiver, plan: ReplayPlan, monitor_adapter: RfMonitorAdapter, at_seconds: float
) -> tuple[list[RfMeasurement], list[RfValidationFinding]]:
    element_windows = _windows_for_array_element(plan, receiver.id)
    if not element_windows:
        # The receiver is a declared TDOA/AOA_DOA array element, but the
        # compiled plan carries no coherent-group coverage for it anywhere
        # (e.g. rogue.compiler.coherent_groups's reference-integrity
        # fallback degraded the link to non-coherent) — a real, always-
        # computable gap, independent of at_seconds.
        return [], [
            RfValidationFinding(
                severity=ValidationSeverity.BLOCKING,
                code="window_not_found",
                message=(
                    f"receiver {receiver.id} ({receiver.receiver_type.value}) has no compiled "
                    "coherent-group coverage in this plan"
                ),
                path="$.rf_windows",
            )
        ]

    measurements: list[RfMeasurement] = []
    findings: list[RfValidationFinding] = []
    for window, channel in element_windows:
        if not (window.start_seconds <= at_seconds < window.end_seconds):
            continue
        allocation = _allocation_for(plan, window)
        measurement = await monitor_adapter.capture(receiver, plan, window, channel, at_seconds)
        measurements.append(measurement)
        findings.extend(
            compare_measurement_to_plan(
                window=window,
                allocation=allocation,
                channel=channel,
                receiver=receiver,
                measurement=measurement,
            )
        )
    return measurements, findings


async def run_validation(
    run: ScenarioRun,
    plan: ReplayPlan,
    receivers: list[Receiver],
    monitor_adapter: RfMonitorAdapter,
    at_seconds: float,
) -> ScenarioRun:
    if run.status not in (RunStatus.RUNNING, RunStatus.STOPPED):
        raise InvalidRunTransitionError(
            RunStatus.RUNNING, run.status, "validate (requires RUNNING or STOPPED)"
        )

    reports = list(run.validation_reports)
    events = list(run.events)
    sequence = len(events)

    for receiver in receivers:
        if receiver.receiver_type == ReceiverType.MONITOR:
            measurements, findings = await _validate_monitor_receiver(
                receiver, plan, monitor_adapter, at_seconds
            )
        else:
            measurements, findings = await _validate_array_element_receiver(
                receiver, plan, monitor_adapter, at_seconds
            )

        if not measurements and not findings:
            continue

        report = RfValidationReport(
            run_id=run.id,
            receiver_id=receiver.id,
            created_at=datetime.now(UTC),
            measurements=measurements,
            findings=findings,
        )
        reports.append(report)

        sequence += 1
        severity = (
            ValidationSeverity.BLOCKING
            if any(f.severity == ValidationSeverity.BLOCKING for f in findings)
            else ValidationSeverity.WARNING
        )
        events.append(
            RunEvent(
                at=datetime.now(UTC),
                sequence=sequence,
                kind=RunEventKind.VALIDATION_RECORDED,
                message=(
                    f"recorded validation report {report.id} for receiver {receiver.id}: "
                    f"{len(measurements)} measurement(s), {len(findings)} finding(s)"
                ),
                severity=severity,
            )
        )

    return run.model_copy(update={"validation_reports": reports, "events": events})
