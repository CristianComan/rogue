"""Independent RF validation evidence (M14).

Per CLAUDE.md rule 15 and docs/architecture/rf-model.md section 9: RF
validation is independent of the replay command path — it observes what a
run actually produced and compares it against the compiled ``ReplayPlan``,
rather than asking the TX ``SDRAdapter`` to self-report. ``rogue.validation``
holds the comparison logic and the ``RfMonitorAdapter`` that produces
``RfMeasurement``s; this module only defines the evidence shapes attached to
``ScenarioRun.validation_reports`` (domain-model.md section 5: run evidence
is append-only).

``RfValidationFinding`` mirrors ``rogue.compiler.models.CompilerFinding``'s
shape (severity/code/message/path), reusing
``rogue.domain.validation.ValidationSeverity`` rather than a third severity
enum.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from rogue.domain.common import IdentifiedMixin, RogueModel
from rogue.domain.validation import ValidationSeverity


class RfValidationFinding(RogueModel):
    """One measured-vs-planned deviation, scoped to a JSON-pointer-like path."""

    severity: ValidationSeverity
    code: str
    message: str
    path: str


class RfMeasurement(IdentifiedMixin):
    """One independent capture against a single ``RfWindow`` or, for a
    TDOA/AOA_DOA array element, a single ``CompositeChannel``.

    ``measured_power_dbfs`` is relative/uncalibrated unless a specific
    ``RfMonitorAdapter`` implementation documents otherwise (rf-model.md
    section 9: "relative/absolute power where calibrated"). ``measured_delay_s``/
    ``measured_phase_rad`` are only meaningful for a TDOA/AOA_DOA array
    element (``receiver_id`` identifies which); both stay ``None`` for a
    MONITOR capture. ``measured_start_offset_s`` is the monitor's own
    detection of the window's start instant, in scenario-time seconds —
    directly comparable to ``RfWindow.start_seconds``/``Allocation.
    start_seconds``, not an offset relative to the capture instant.
    """

    receiver_id: UUID
    window_key: str
    captured_at: datetime
    measured_center_frequency_hz: float
    measured_bandwidth_hz: float
    measured_power_dbfs: float | None = None
    measured_start_offset_s: float | None = None
    measured_delay_s: float | None = None
    measured_phase_rad: float | None = None
    underrun_detected: bool = False


class RfValidationReport(IdentifiedMixin):
    """One independent validation pass for one ``Receiver`` against one run."""

    run_id: UUID
    receiver_id: UUID
    created_at: datetime
    measurements: list[RfMeasurement]
    findings: list[RfValidationFinding]
