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

from rogue.compiler.coherent_groups import compute_doppler_schedule, expand_occupied_bands
from rogue.compiler.frequency import realize_frequency_timeline
from rogue.compiler.models import (
    CompilerFinding,
    CompositeChannel,
    HardwareCapabilityProfile,
    RfWindow,
)
from rogue.domain.mission_evaluator import zone_crossings
from rogue.domain.recording import IQRecording
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.models import OccupiedBand
from rogue.spectrum.occupancy import RecordingKey, compute_spectrum_state

DEFAULT_GUARD_MARGIN_HZ = 100_000.0


def _boundary_seconds(
    version: ScenarioVersion, recordings: Mapping[RecordingKey, IQRecording], duration_s: float
) -> tuple[list[float], list[CompilerFinding]]:
    """Every instant within [0, duration_s) where occupancy can change.

    A ``zone_trigger`` emission (ADR-015) has no ``start_offset``/
    ``duration_override`` to read (both fixed at their defaults by
    ``RfEmission``'s own mutual-exclusion validator) — its on/off instants
    come from ``mission_evaluator.zone_crossings`` scanning the whole
    ``[0, duration_s)`` horizon instead, one call per zone-triggered
    emission. An unresolvable ``zone_trigger.zone_id`` contributes no
    boundaries (reference integrity is ``validate_scenario_version``'s job,
    not this function's — same precedent as ``array_group_id``).

    A mission ``zone_crossings`` can't evaluate (unsupported template or
    start policy) is different: this function *must* report a BLOCKING
    finding here directly, rather than counting on ``compute_spectrum_state``
    to hit the same error at whatever boundaries do get evaluated — for a
    mission whose ``AT_TIME_OFFSET`` start falls after every boundary this
    function does discover (e.g. only ``{0.0, duration_s}`` survive),
    ``evaluate_mission_position`` never actually reaches the unsupported-
    template branch at either of those instants (both fall in its "before
    start" early return), so the error would otherwise never surface at
    all — silently producing no window and no finding, exactly the "quiet
    failure" CLAUDE.md rule 12's default-deny is meant to prevent.
    """
    boundaries = {0.0, duration_s}
    findings: list[CompilerFinding] = []
    zones_by_id = {zone.id: zone for zone in version.zones}
    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            for event in realize_frequency_timeline(link, duration_s):
                if 0.0 <= event.at_seconds < duration_s:
                    boundaries.add(event.at_seconds)
            for emission_index, emission in enumerate(link.emissions):
                if emission.zone_trigger is not None:
                    zone = zones_by_id.get(emission.zone_trigger.zone_id)
                    if zone is None:
                        continue
                    try:
                        crossings = zone_crossings(mission, zone.polygon, 0.0, duration_s)
                    except NotImplementedError as exc:
                        findings.append(
                            CompilerFinding(
                                severity=ValidationSeverity.BLOCKING,
                                code="zone_trigger_position_unresolvable",
                                message=(
                                    "cannot evaluate zone_trigger emission timing over "
                                    f"[0, {duration_s}s): {exc}"
                                ),
                                path=(
                                    f"missions[{mission_index}].rf_links[{link_index}]"
                                    f".emissions[{emission_index}].zone_trigger"
                                ),
                            )
                        )
                        continue
                    for interval_start, interval_end in crossings:
                        if 0.0 <= interval_start < duration_s:
                            boundaries.add(interval_start)
                        if 0.0 < interval_end < duration_s:
                            boundaries.add(interval_end)
                    continue

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
    return sorted(boundaries), findings


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
            # Two elements of the same coherent group (ADR-012) must never
            # share one physical channel's window — they need to land on
            # *different* channels simultaneously, unlike ADR-003's normal
            # same-channel sharing of otherwise-unrelated signals. They are
            # frequency-identical (same link/emission), so without this
            # guard they'd merge here just like any other frequency-
            # adjacent pair.
            same_coherent_group = band.coherent_group_id is not None and any(
                b.coherent_group_id == band.coherent_group_id for b in group
            )
            if (
                band.freq_min_hz - group_max <= DEFAULT_GUARD_MARGIN_HZ
                and span <= max_window_bandwidth_hz
                and not same_coherent_group
            ):
                group.append(band)
                placed = True
        if not placed:
            groups.append([band])

    windows: list[tuple[str, float, float, list[OccupiedBand]]] = []
    for group in groups:
        freq_min = min(b.freq_min_hz for b in group) - DEFAULT_GUARD_MARGIN_HZ / 2
        freq_max = max(b.freq_max_hz for b in group) + DEFAULT_GUARD_MARGIN_HZ / 2
        # A coherent group's per-element bands share one link_id, which
        # would otherwise collide into one non-unique window_key across
        # elements — fold in the target receiver id to disambiguate.
        window_key = "|".join(
            sorted(
                f"{b.link_id}:coherent:{b.array_element_receiver_id}"
                if b.array_element_receiver_id is not None
                else str(b.link_id)
                for b in group
            )
        )
        windows.append((window_key, (freq_min + freq_max) / 2, freq_max - freq_min, group))
    return windows, findings


def _attach_doppler_schedules(
    windows: list[RfWindow], version: ScenarioVersion
) -> tuple[list[RfWindow], list[CompilerFinding]]:
    """Fill in each coherent channel's ``doppler_schedule`` (M12, ADR-013),
    now that every window's true final ``[start_seconds, end_seconds)``
    span is known — window-coalescing above can extend a span past the one
    instant ``rogue.compiler.coherent_groups.expand_occupied_bands`` saw it
    at, so only this later, whole-window pass can span it correctly.
    """
    findings: list[CompilerFinding] = []
    receivers_by_id = {r.id: r for r in version.receivers}
    missions_by_id = {m.id: m for m in version.missions}

    result: list[RfWindow] = []
    for window in windows:
        updated_channels: list[CompositeChannel] = []
        for channel in window.channels:
            if channel.array_element_receiver_id is None:
                updated_channels.append(channel)
                continue
            receiver = receivers_by_id.get(channel.array_element_receiver_id)
            mission = missions_by_id.get(channel.mission_id)
            if receiver is None or mission is None:
                updated_channels.append(channel)
                continue
            try:
                schedule = compute_doppler_schedule(
                    receiver,
                    mission,
                    window.start_seconds,
                    window.end_seconds,
                    channel.center_frequency_hz,
                )
            except NotImplementedError as exc:
                findings.append(
                    CompilerFinding(
                        severity=ValidationSeverity.BLOCKING,
                        code="coherent_group_doppler_unresolvable",
                        message=(
                            f"cannot compute Doppler schedule for link {channel.link_id} in "
                            f"window {window.window_key}: {exc}"
                        ),
                        path="$",
                    )
                )
                updated_channels.append(channel)
                continue
            updated_channels.append(channel.model_copy(update={"doppler_schedule": schedule}))
        result.append(window.model_copy(update={"channels": updated_channels}))
    return result, findings


def compute_rf_windows(
    version: ScenarioVersion,
    recordings: Mapping[RecordingKey, IQRecording],
    duration_s: float,
    capability_profile: HardwareCapabilityProfile,
) -> tuple[list[RfWindow], list[CompilerFinding]]:
    """Compute the RF window schedule over [0, duration_s)."""
    boundaries, findings = _boundary_seconds(version, recordings, duration_s)

    open_windows: dict[str, RfWindow] = {}
    closed_windows: list[RfWindow] = []

    for index, t in enumerate(boundaries[:-1]):
        next_t = boundaries[index + 1]
        state = compute_spectrum_state(version, t, recordings)
        for f in state.findings:
            findings.append(
                CompilerFinding(severity=f.severity, code=f.code, message=f.message, path=f.path)
            )

        expanded_bands, expand_findings = expand_occupied_bands(state.occupied_bands, version, t)
        findings.extend(expand_findings)

        packed, pack_findings = _pack_bands(expanded_bands, capability_profile, path="$")
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
                    recording=b.recording,
                    observed_by_receiver_id=b.observed_by_receiver_id,
                    coherent_group_id=b.coherent_group_id,
                    array_element_receiver_id=b.array_element_receiver_id,
                    phase_offset_rad=b.phase_offset_rad,
                    delay_offset_s=b.delay_offset_s,
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

    with_doppler, doppler_findings = _attach_doppler_schedules(closed_windows, version)
    findings.extend(doppler_findings)
    return with_doppler, findings
