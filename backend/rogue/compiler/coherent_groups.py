"""Coherent-group RF window expansion for TDOA/AOA_DOA receivers (ADR-012).

Expands one ``OccupiedBand`` belonging to a ``DroneRfLink`` with
``array_group_id`` set into N per-``Receiver``-element bands (one per
``Receiver`` sharing that ``array_group_id``), each carrying a computed
phase (AOA_DOA only) and delay offset relative to the group's reference
element — the transmit-side counterpart to ``Receiver.array_group_id``'s
receiver-side grouping. Called by
``rogue.compiler.windows.compute_rf_windows`` before ``_pack_bands`` runs,
so a coherent group's N elements are packed into N separate ``RfWindow``s
(never merged — see ``windows.py``'s ``_pack_bands`` guard) ready for
``rogue.compiler.allocation``'s atomic group-allocation pass.

Phase and delay are computed once per call (i.e. once per ``RfWindow`` span,
at the span's ``start_seconds``) from the transmitter's position at that
instant (``rogue.domain.mission_evaluator.evaluate_mission_position``) — a
piecewise-constant approximation good for the granularity ``RfWindow``
spans already discretize time at (delay changes negligibly within one
window at realistic drone speeds). Doppler shift (M12, ADR-013) is
different: ``compute_doppler_schedule`` below produces several samples
across a window's span rather than one, because the whole point is
applying it as a *continuous* per-sample NCO during streaming
(``agents/common/dsp.py``) — it is computed separately, once each
``RfWindow``'s final span is known, by ``rogue.compiler.windows`` (not
inline here, since window-coalescing can extend a span after this module's
per-instant expansion already ran).

Reference-integrity (an ``array_group_id`` must resolve to >=2 TDOA/AOA_DOA
receivers) is validated separately by
``rogue.domain.validation.validate_scenario_version`` at publish time; this
module is defensive but not authoritative about it — an unresolvable group
here degrades to treating the band as non-coherent (one band, unchanged)
rather than raising.
"""

from __future__ import annotations

import math
from uuid import UUID

from rogue.compiler.models import CompilerFinding, DopplerSample
from rogue.domain.common import GeoPoint
from rogue.domain.geometry import (
    SPEED_OF_LIGHT_MPS,
    haversine_distance_m,
    horizontal_los_unit_vector,
)
from rogue.domain.mission import DroneMission
from rogue.domain.mission_evaluator import evaluate_mission_position
from rogue.domain.receiver import Receiver, ReceiverType
from rogue.domain.rf import DroneRfLink
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.models import OccupiedBand

# Doppler schedule sampling (M12, ADR-013): a fixed cadence, capped for very
# long windows so a plan's size stays bounded regardless of scenario
# duration — a documented granularity choice, not a claim that Doppler
# actually changes in discrete steps.
DOPPLER_SCHEDULE_STEP_SECONDS = 1.0
MAX_DOPPLER_SCHEDULE_SAMPLES = 61
# Finite-difference step for range-rate estimation — same two-sample
# technique as frontend/src/domain/doppler.ts:rangeAndRangeRate.
_RANGE_RATE_DT_SECONDS = 0.05


def reference_receiver(members: list[Receiver]) -> Receiver:
    """The group's phase/delay reference element.

    ``element_index`` is optional even on array-type receivers
    (``rogue.domain.receiver`` validates ``array_group_id``/
    ``element_local_offset_m``, not ``element_index``) — sorting ``None``
    last, then by receiver id, keeps this deterministic (CLAUDE.md rule 14)
    without requiring authors to fill in ``element_index``.
    """
    return min(
        members,
        key=lambda r: (r.element_index if r.element_index is not None else 2**31, str(r.id)),
    )


def compute_delay_offset_s(element: Receiver, reference: Receiver, tx_position: GeoPoint) -> float:
    """Δτ = (|p_tx - p_element| - |p_tx - p_reference|) / c — rf-model.md section 6."""
    if element.id == reference.id:
        return 0.0
    d_element = haversine_distance_m(tx_position, element.position)
    d_reference = haversine_distance_m(tx_position, reference.position)
    return (d_element - d_reference) / SPEED_OF_LIGHT_MPS


def compute_phase_offset_rad(
    element: Receiver, reference: Receiver, tx_position: GeoPoint, carrier_hz: float
) -> float | None:
    """AOA_DOA only (needs ``element_local_offset_m``); ``None`` for TDOA elements.

    Projects the element's local-frame offset from the reference element
    onto the horizontal transmitter line-of-sight unit vector (from the
    reference position), ``phase = 2*pi/lambda * projected_offset_m``.
    This sign convention (offset toward the transmitter -> advanced phase)
    is a documented design choice — rf-model.md section 6 gives no formula
    at all for AOA/DOA — matching a standard phased-array steering-vector
    form, not a claim of the only correct convention.
    """
    if element.element_local_offset_m is None or reference.element_local_offset_m is None:
        return None
    if element.id == reference.id:
        return 0.0

    east, north = horizontal_los_unit_vector(reference.position, tx_position)
    d_east = element.element_local_offset_m[0] - reference.element_local_offset_m[0]
    d_north = element.element_local_offset_m[1] - reference.element_local_offset_m[1]
    projected_offset_m = d_east * east + d_north * north

    wavelength_m = SPEED_OF_LIGHT_MPS / carrier_hz
    return 2 * math.pi / wavelength_m * projected_offset_m


def _range_rate_mps(receiver: Receiver, mission: DroneMission, at_seconds: float) -> float:
    """Instantaneous rate of change of the transmitter-to-receiver range, in
    m/s (positive = receding), via two-sample finite difference — mirrors
    frontend/src/domain/doppler.ts:rangeAndRangeRate exactly, so backend and
    frontend agree on the same figure for the same inputs.
    """
    p_before = evaluate_mission_position(mission, at_seconds)
    p_after = evaluate_mission_position(mission, at_seconds + _RANGE_RATE_DT_SECONDS)
    range_before = haversine_distance_m(p_before, receiver.position)
    range_after = haversine_distance_m(p_after, receiver.position)
    return (range_after - range_before) / _RANGE_RATE_DT_SECONDS


def compute_doppler_schedule(
    receiver: Receiver,
    mission: DroneMission,
    window_start: float,
    window_end: float,
    carrier_hz: float,
) -> list[DopplerSample]:
    """A Doppler-shift schedule for ``receiver`` observing ``mission``'s
    transmitter across ``[window_start, window_end)`` (M12, ADR-013).

    Unlike ``compute_delay_offset_s``/``compute_phase_offset_rad``, this
    needs no "reference element" — Doppler shift is an absolute quantity
    per (transmitter, receiver) pair, computed the same way for TDOA and
    AOA_DOA elements alike (it doesn't depend on ``element_local_offset_m``).

    ``doppler_shift_hz = -range_rate_mps / c * carrier_hz``: receding
    (positive range-rate) yields a *negative* shift (red-shift, lower
    frequency); closing yields positive (blue-shift) — the standard physics
    convention, opposite in sign from the frontend's "positive range-rate =
    receding" convention for range-rate itself (only the shift's sign
    flips; range-rate's own sign convention is unchanged and shared).
    """
    span = max(0.0, window_end - window_start)
    sample_count = max(
        2, min(MAX_DOPPLER_SCHEDULE_SAMPLES, math.ceil(span / DOPPLER_SCHEDULE_STEP_SECONDS) + 1)
    )
    samples = []
    for i in range(sample_count):
        t_offset = span * i / (sample_count - 1) if sample_count > 1 else 0.0
        range_rate = _range_rate_mps(receiver, mission, window_start + t_offset)
        doppler_shift_hz = -range_rate / SPEED_OF_LIGHT_MPS * carrier_hz
        samples.append(DopplerSample(t_offset_seconds=t_offset, doppler_shift_hz=doppler_shift_hz))
    return samples


def expand_occupied_bands(
    bands: list[OccupiedBand], version: ScenarioVersion, at_seconds: float
) -> tuple[list[OccupiedBand], list[CompilerFinding]]:
    """Expand each coherent-link band into one per matching Receiver element.

    A band whose link has no ``array_group_id``, or whose ``array_group_id``
    doesn't resolve to >=2 receivers, passes through unchanged (reference-
    integrity is authoritatively checked by ``validate_scenario_version``,
    not here). A mission template ``rogue.domain.mission_evaluator`` can't
    evaluate a position for degrades the same way, with a BLOCKING finding
    naming the gap, rather than crashing the compile.
    """
    findings: list[CompilerFinding] = []
    links_by_id: dict[UUID, DroneRfLink] = {}
    mission_by_link_id: dict[UUID, DroneMission] = {}
    for mission in version.missions:
        for rf_link in mission.rf_links:
            links_by_id[rf_link.id] = rf_link
            mission_by_link_id[rf_link.id] = mission

    receivers_by_group: dict[UUID, list[Receiver]] = {}
    for receiver in version.receivers:
        if receiver.array_group_id is not None:
            receivers_by_group.setdefault(receiver.array_group_id, []).append(receiver)

    expanded: list[OccupiedBand] = []
    for band in bands:
        link = links_by_id.get(band.link_id)
        members = (
            receivers_by_group.get(link.array_group_id)
            if link is not None and link.array_group_id is not None
            else None
        )
        if link is None or link.array_group_id is None or not members or len(members) < 2:
            expanded.append(band)
            continue

        mission = mission_by_link_id[band.link_id]
        try:
            tx_position = evaluate_mission_position(mission, at_seconds)
        except NotImplementedError as exc:
            findings.append(
                CompilerFinding(
                    severity=ValidationSeverity.BLOCKING,
                    code="coherent_group_position_unresolvable",
                    message=(
                        f"cannot compute coherent-group phase/delay for link {band.link_id}: {exc}"
                    ),
                    path="$",
                )
            )
            expanded.append(band)
            continue

        reference = reference_receiver(members)
        for element in members:
            expanded.append(
                band.model_copy(
                    update={
                        "coherent_group_id": link.array_group_id,
                        "array_element_receiver_id": element.id,
                        "phase_offset_rad": (
                            compute_phase_offset_rad(
                                element, reference, tx_position, band.center_frequency_hz
                            )
                            if element.receiver_type == ReceiverType.AOA_DOA
                            else None
                        ),
                        "delay_offset_s": compute_delay_offset_s(element, reference, tx_position),
                    }
                )
            )

    return expanded, findings
