"""RF window packing for the RF Environment Compiler (M6).

Reuses M5's ``compute_spectrum_state`` (``rogue.spectrum.occupancy``)
evaluated at each instant occupancy can change — realized-frequency-event
and emission start/end boundaries — since occupancy is otherwise
piecewise-constant between those instants (ADR-003). Adjacent instants that
produce an identical set of windows are coalesced into one ``RfWindow``
span, so the output is a genuine schedule rather than a per-instant dump.
Any ``SpectrumFinding`` M5 already surfaces (frequency_unresolved,
recording_unavailable, bandwidth_exceeds_band, spectral_overlap) is carried
through as a ``CompilerFinding`` with the same code/severity.

The packing algorithm (greedy, sorted-by-frequency, guard-margin merge) and
window-identity scheme (link-id-set as ``window_key``) are compiler
assumptions — rf-model.md only specifies "fit within usable bandwidth and
guard margins" (ADR-003), not an algorithm. See docs/decisions/ADR-006 for
the exact choice and its limits (no intermodulation/aggregate-power
modelling; first-fit only).
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from rogue.compiler.frequency import realize_frequency_timeline
from rogue.compiler.models import (
    CompilerFinding,
    CompositeChannel,
    HardwareCapabilityProfile,
    RfWindow,
)
from rogue.domain.recording import IQRecording
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.models import OccupiedBand
from rogue.spectrum.occupancy import RecordingKey, compute_spectrum_state

DEFAULT_GUARD_MARGIN_HZ = 100_000.0


def _boundary_seconds(
    version: ScenarioVersion, recordings: Mapping[RecordingKey, IQRecording], duration_s: float
) -> list[float]:
    """Every instant within [0, duration_s) where occupancy can change."""
    boundaries = {0.0, duration_s}
    for mission in version.missions:
        for link in mission.rf_links:
            for event in realize_frequency_timeline(link, duration_s):
                if 0.0 <= event.at_seconds < duration_s:
                    boundaries.add(event.at_seconds)
            for emission in link.emissions:
                start = emission.start_offset.total_seconds()
                if 0.0 <= start < duration_s:
                    boundaries.add(start)
                if emission.loop or emission.recording is None:
                    continue
                if emission.duration_override is not None:
                    end = start + emission.duration_override.total_seconds()
                else:
                    key = (emission.recording.recording_id, emission.recording.version)
                    recording = recordings.get(key)
                    if recording is None:
                        continue
                    end = start + recording.duration_s
                if 0.0 < end < duration_s:
                    boundaries.add(end)
    return sorted(boundaries)


def _pack_bands(
    bands: list[OccupiedBand], capability_profile: HardwareCapabilityProfile, path: str
) -> tuple[list[tuple[str, float, float, list[OccupiedBand]]], list[CompilerFinding]]:
    """Group co-occurring bands into windows: (window_key, center_hz, bandwidth_hz, bands)."""
    findings: list[CompilerFinding] = []
    if not capability_profile.channels:
        return [], findings
    max_window_bandwidth_hz = max(c.max_usable_bandwidth_hz for c in capability_profile.channels)

    groups: list[list[OccupiedBand]] = []
    for band in sorted(bands, key=lambda b: b.freq_min_hz):
        if band.bandwidth_hz > max_window_bandwidth_hz:
            findings.append(
                CompilerFinding(
                    severity=ValidationSeverity.BLOCKING,
                    code="rf_window_infeasible",
                    message=(
                        f"emission {band.emission_id}'s occupied bandwidth {band.bandwidth_hz} Hz "
                        f"exceeds the widest configured physical channel "
                        f"({max_window_bandwidth_hz} Hz) — no RF window can carry it"
                    ),
                    path=path,
                )
            )
            continue

        placed = False
        if groups:
            group = groups[-1]
            group_min = min(b.freq_min_hz for b in group)
            group_max = max(b.freq_max_hz for b in group)
            span = max(group_max, band.freq_max_hz) - min(group_min, band.freq_min_hz)
            if (
                band.freq_min_hz - group_max <= DEFAULT_GUARD_MARGIN_HZ
                and span <= max_window_bandwidth_hz
            ):
                group.append(band)
                placed = True
        if not placed:
            groups.append([band])

    windows: list[tuple[str, float, float, list[OccupiedBand]]] = []
    for group in groups:
        freq_min = min(b.freq_min_hz for b in group) - DEFAULT_GUARD_MARGIN_HZ / 2
        freq_max = max(b.freq_max_hz for b in group) + DEFAULT_GUARD_MARGIN_HZ / 2
        window_key = "|".join(sorted(str(b.link_id) for b in group))
        windows.append((window_key, (freq_min + freq_max) / 2, freq_max - freq_min, group))
    return windows, findings


def compute_rf_windows(
    version: ScenarioVersion,
    recordings: Mapping[RecordingKey, IQRecording],
    duration_s: float,
    capability_profile: HardwareCapabilityProfile,
) -> tuple[list[RfWindow], list[CompilerFinding]]:
    """Compute the RF window schedule over [0, duration_s)."""
    findings: list[CompilerFinding] = []
    boundaries = _boundary_seconds(version, recordings, duration_s)

    open_windows: dict[str, RfWindow] = {}
    closed_windows: list[RfWindow] = []

    for index, t in enumerate(boundaries[:-1]):
        next_t = boundaries[index + 1]
        state = compute_spectrum_state(version, t, recordings)
        for f in state.findings:
            findings.append(
                CompilerFinding(severity=f.severity, code=f.code, message=f.message, path=f.path)
            )

        packed, pack_findings = _pack_bands(state.occupied_bands, capability_profile, path="$")
        findings.extend(pack_findings)

        current_keys = {window_key for window_key, *_ in packed}
        for window_key in list(open_windows):
            if window_key not in current_keys:
                closed_windows.append(open_windows.pop(window_key))

        for window_key, center, bandwidth, group in packed:
            channels = [
                CompositeChannel(
                    mission_id=b.mission_id,
                    link_id=b.link_id,
                    role=b.role,
                    emission_id=b.emission_id,
                    center_frequency_hz=b.center_frequency_hz,
                    bandwidth_hz=b.bandwidth_hz,
                    gain_offset_db=0.0,
                )
                for b in group
            ]
            existing = open_windows.get(window_key)
            if (
                existing is not None
                and existing.center_frequency_hz == center
                and existing.bandwidth_hz == bandwidth
            ):
                open_windows[window_key] = existing.model_copy(update={"end_seconds": next_t})
            else:
                if existing is not None:
                    closed_windows.append(existing)
                open_windows[window_key] = RfWindow(
                    id=uuid4(),
                    window_key=window_key,
                    start_seconds=t,
                    end_seconds=next_t,
                    center_frequency_hz=center,
                    bandwidth_hz=bandwidth,
                    channels=channels,
                )

    closed_windows.extend(open_windows.values())
    closed_windows.sort(key=lambda w: (w.start_seconds, w.window_key))
    return closed_windows, findings
