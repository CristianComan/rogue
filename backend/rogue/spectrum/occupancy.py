"""Deterministic spectrum occupancy and conflict/headroom computation (M5).

Pure functions only — no DB/I/O. Recording metadata (needed for occupied
bandwidth) is passed in already resolved, mirroring how
``rogue.domain.validation.validate_scenario_version`` operates on an
in-memory ``ScenarioVersion`` without doing its own I/O; callers (see
``rogue.persistence.spectrum``) fetch recordings first.

Frequency resolution per ``FrequencySwitchingMode``:

- ``SCRIPTED``: piecewise-constant over ``scripted_changes``, same semantics
  as ``frontend/src/domain/spectrumStrip.ts::currentFrequencyHz`` (defaults
  to ``band.freq_min_hz`` before the first change), so the authored-preview
  and compiled views agree.
- ``PROBABILISTIC_ADAPTIVE``: deterministic dwell sequence seeded by
  ``random_seed``. **This dwell algorithm is an assumption** — neither
  ``rogue.domain.rf`` nor docs/architecture/rf-model.md specify one, only
  that it must be "deterministic when seed is fixed". Dwell durations are
  drawn from an exponential distribution with mean ``mean_dwell_s`` via
  ``random.Random(seed)``; the channel for each dwell is picked uniformly
  from ``band.allowed_channels_hz``. Requires a non-empty
  ``allowed_channels_hz`` — without an explicit channel plan there is
  nothing to switch between, so this mode is unresolved instead of
  inventing one. The dwell-generation loop itself lives in the public
  ``probabilistic_dwell_segments`` so ``rogue.compiler.frequency`` (M6) can
  realize the same seeded sequence over a full compile horizon rather than
  one instant at a time.
- ``MISSION_TRIGGERED`` / ``EXTERNAL_STATE_TRIGGERED``: always unresolved.
  The backend has no mission-time-evaluation engine yet (that logic only
  exists on the frontend, ``frontend/src/domain/missionEvaluator.ts`` — see
  ``rogue.domain.mission``'s module docstring) and external trigger state
  isn't available at planning time, so these are reported as an explicit
  finding rather than silently defaulted to something misleading.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from itertools import combinations
from math import log
from uuid import UUID

from rogue.domain.recording import IQRecording
from rogue.domain.rf import DroneRfLink, FrequencySwitchingMode, RfEmission
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.validation import ValidationSeverity
from rogue.spectrum.models import FrequencyResolution, OccupiedBand, SpectrumFinding, SpectrumState

RecordingKey = tuple[UUID, int]


def _resolve_scripted(link: DroneRfLink, at_seconds: float) -> FrequencyResolution:
    changes = sorted(link.frequency_behaviour.scripted_changes, key=lambda c: c.at_offset)
    current = link.band.freq_min_hz
    for change in changes:
        if change.at_offset.total_seconds() > at_seconds:
            break
        current = change.frequency_hz
    return FrequencyResolution(link_id=link.id, resolved=True, frequency_hz=current)


def probabilistic_dwell_segments(
    random_seed: int, mean_dwell_s: float, allowed_channels_hz: list[float], up_to_seconds: float
) -> list[tuple[float, float, float]]:
    """(start, end, frequency_hz) dwell segments covering at least [0, up_to_seconds].

    Extracted from ``_resolve_probabilistic`` so there is one seeded-RNG
    implementation of PROBABILISTIC_ADAPTIVE dwell semantics, reused by
    ``_resolve_probabilistic`` itself (single-instant query — takes the last
    segment) and by ``rogue.compiler.frequency`` (M6, full-horizon
    realization). The final segment's end may exceed ``up_to_seconds`` by up
    to one dwell (the natural stopping point isn't known in advance);
    callers needing a hard-clipped horizon truncate it themselves.
    """
    rng = random.Random(random_seed)
    segments: list[tuple[float, float, float]] = []
    t = 0.0
    current = rng.choice(allowed_channels_hz)
    while True:
        # Exponential inter-event time via inverse-CDF sampling from rng's
        # own uniform stream (rather than rng.expovariate) so the sequence
        # only ever depends on (seed, mean_dwell_s), not on stdlib internals
        # calling the uniform stream a different number of times per draw.
        u = rng.random()
        dwell = -mean_dwell_s * log(1.0 - u)
        next_t = t + dwell
        segments.append((t, next_t, current))
        if next_t > up_to_seconds:
            break
        t = next_t
        current = rng.choice(allowed_channels_hz)
    return segments


def _resolve_probabilistic(link: DroneRfLink, at_seconds: float) -> FrequencyResolution:
    behaviour = link.frequency_behaviour
    channels = link.band.allowed_channels_hz
    if not channels:
        return FrequencyResolution(
            link_id=link.id,
            resolved=False,
            unresolved_reason="PROBABILISTIC_ADAPTIVE requires band.allowed_channels_hz",
        )
    assert behaviour.random_seed is not None  # enforced by FrequencyBehaviour's own validator

    mean_dwell_s = behaviour.mean_dwell_s
    if mean_dwell_s is None or mean_dwell_s <= 0:
        return FrequencyResolution(
            link_id=link.id,
            resolved=False,
            unresolved_reason="PROBABILISTIC_ADAPTIVE requires a positive mean_dwell_s",
        )

    segments = probabilistic_dwell_segments(
        behaviour.random_seed, mean_dwell_s, channels, at_seconds
    )
    return FrequencyResolution(link_id=link.id, resolved=True, frequency_hz=segments[-1][2])


def resolve_frequency_hz(link: DroneRfLink, at_seconds: float) -> FrequencyResolution:
    """Resolve the frequency a link would be transmitting on at ``at_seconds``."""
    mode = link.frequency_behaviour.mode
    if mode == FrequencySwitchingMode.SCRIPTED:
        return _resolve_scripted(link, at_seconds)
    if mode == FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE:
        return _resolve_probabilistic(link, at_seconds)
    reason = {
        FrequencySwitchingMode.MISSION_TRIGGERED: (
            "MISSION_TRIGGERED requires the mission-time-evaluation engine, not yet "
            "implemented on the backend (M3 only ported this to the frontend)"
        ),
        FrequencySwitchingMode.EXTERNAL_STATE_TRIGGERED: (
            "EXTERNAL_STATE_TRIGGERED requires runtime external-trigger integration, "
            "not available at planning time"
        ),
    }[mode]
    return FrequencyResolution(link_id=link.id, resolved=False, unresolved_reason=reason)


def active_emission_at(
    link: DroneRfLink, at_seconds: float, recordings: Mapping[RecordingKey, IQRecording]
) -> RfEmission | None:
    """The emission (if any) actively transmitting on ``link`` at ``at_seconds``.

    A link isn't necessarily always transmitting — no active emission is a
    normal outcome, not a finding. Effective duration prefers
    ``duration_override``; otherwise it needs the referenced recording's
    ``duration_s``. If neither is available (the recording isn't in
    ``recordings``), the emission is conservatively treated as active once
    started rather than silently treated as idle — the caller
    (``compute_spectrum_state``) still surfaces the missing recording as a
    ``recording_unavailable`` finding when it tries to compute bandwidth.
    """
    for emission in link.emissions:
        start = emission.start_offset.total_seconds()
        if at_seconds < start:
            continue
        if emission.loop:
            return emission

        if emission.duration_override is not None:
            duration: float | None = emission.duration_override.total_seconds()
        else:
            # RfEmission's own model validator requires duration_override
            # whenever recording is None, so reaching here means recording
            # is set.
            assert emission.recording is not None
            key = (emission.recording.recording_id, emission.recording.version)
            recording = recordings.get(key)
            duration = recording.duration_s if recording is not None else None

        if duration is None or (at_seconds - start) < duration:
            return emission
    return None


def _headroom_hz(link: DroneRfLink, bandwidth_hz: float) -> float:
    band_width = link.band.freq_max_hz - link.band.freq_min_hz
    return max(0.0, band_width - bandwidth_hz)


def compute_spectrum_state(
    version: ScenarioVersion,
    at_seconds: float,
    recordings: Mapping[RecordingKey, IQRecording],
) -> SpectrumState:
    """Compute deterministic spectrum occupancy and conflict/headroom findings.

    Per CLAUDE.md non-negotiable rule 5, spectral overlap between links is
    legal by default and is reported as an advisory (WARNING) finding, never
    BLOCKING. A resolved occupied band that doesn't fit inside its own
    link's declared ``RfBand`` is BLOCKING — that's a domain-integrity
    problem (the band is too narrow for what it's carrying), not a policy
    call about intentional overlap.
    """
    occupied_bands: list[OccupiedBand] = []
    findings: list[SpectrumFinding] = []

    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            path = f"missions[{mission_index}].rf_links[{link_index}]"

            emission = active_emission_at(link, at_seconds, recordings)
            if emission is None:
                continue
            if emission.recording is None:
                # An explicit silence span (RfEmission.recording is None): the
                # link is deliberately off-air, not an error condition.
                continue

            resolution = resolve_frequency_hz(link, at_seconds)
            if not resolution.resolved:
                findings.append(
                    SpectrumFinding(
                        severity=ValidationSeverity.WARNING,
                        code="frequency_unresolved",
                        message=(
                            f"could not resolve link frequency at t={at_seconds}s: "
                            f"{resolution.unresolved_reason}"
                        ),
                        path=path,
                    )
                )
                continue

            recording_key = (emission.recording.recording_id, emission.recording.version)
            recording = recordings.get(recording_key)
            if recording is None:
                findings.append(
                    SpectrumFinding(
                        severity=ValidationSeverity.WARNING,
                        code="recording_unavailable",
                        message=(
                            f"recording {recording_key[0]} v{recording_key[1]} referenced by the "
                            "active emission is unavailable; occupied bandwidth cannot be computed"
                        ),
                        path=path,
                    )
                )
                continue

            assert resolution.frequency_hz is not None
            center = resolution.frequency_hz
            bandwidth = recording.sample_rate_hz
            freq_min = center - bandwidth / 2
            freq_max = center + bandwidth / 2

            occupied_bands.append(
                OccupiedBand(
                    mission_id=mission.id,
                    link_id=link.id,
                    role=link.role,
                    emission_id=emission.id,
                    center_frequency_hz=center,
                    bandwidth_hz=bandwidth,
                    freq_min_hz=freq_min,
                    freq_max_hz=freq_max,
                    headroom_hz=_headroom_hz(link, bandwidth),
                )
            )

            if freq_min < link.band.freq_min_hz or freq_max > link.band.freq_max_hz:
                findings.append(
                    SpectrumFinding(
                        severity=ValidationSeverity.BLOCKING,
                        code="bandwidth_exceeds_band",
                        message=(
                            f"occupied band [{freq_min}, {freq_max}] Hz falls outside the link's "
                            f"declared band [{link.band.freq_min_hz}, {link.band.freq_max_hz}] Hz"
                        ),
                        path=path,
                    )
                )

    for a, b in combinations(occupied_bands, 2):
        if a.freq_min_hz < b.freq_max_hz and b.freq_min_hz < a.freq_max_hz:
            findings.append(
                SpectrumFinding(
                    severity=ValidationSeverity.WARNING,
                    code="spectral_overlap",
                    message=(
                        f"link {a.link_id}'s occupied band [{a.freq_min_hz}, {a.freq_max_hz}] Hz "
                        f"overlaps link {b.link_id}'s [{b.freq_min_hz}, {b.freq_max_hz}] Hz — "
                        "overlap may be intentional, this is advisory only"
                    ),
                    path="$",
                )
            )

    return SpectrumState(at_seconds=at_seconds, occupied_bands=occupied_bands, findings=findings)
