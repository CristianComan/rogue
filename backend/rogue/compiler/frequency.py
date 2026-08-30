"""Realized frequency-agility timelines for the RF Environment Compiler (M6).

SCRIPTED links are walked directly from their authored
``scripted_changes`` (fully deterministic, no RNG — simpler than
round-tripping through a segment abstraction). PROBABILISTIC_ADAPTIVE links
reuse ``rogue.spectrum.occupancy.probabilistic_dwell_segments`` — the same
seeded-RNG dwell generator backing M5's single-instant
``resolve_frequency_hz`` — so the compiled Replay Plan and the M5 preview
never diverge on what a link would be doing at a given time.

MISSION_TRIGGERED and EXTERNAL_STATE_TRIGGERED links realize to an empty
timeline: the backend has no mission-time-evaluation engine (M3) and no
external trigger state at compile time, matching
``rogue.spectrum.occupancy.resolve_frequency_hz``'s limitation. Callers
surface an empty/unresolved timeline for an active link as a compiler
finding.
"""

from __future__ import annotations

from rogue.compiler.models import RealizedFrequencyEvent
from rogue.domain.rf import DroneRfLink, FrequencySwitchingMode
from rogue.domain.rf import FrequencyTransitionType as TransitionType
from rogue.spectrum.occupancy import probabilistic_dwell_segments


def _realize_scripted(link: DroneRfLink, duration_s: float) -> list[RealizedFrequencyEvent]:
    changes = sorted(link.frequency_behaviour.scripted_changes, key=lambda c: c.at_offset)
    events: list[RealizedFrequencyEvent] = []

    if not changes or changes[0].at_offset.total_seconds() > 0.0:
        events.append(
            RealizedFrequencyEvent(
                link_id=link.id,
                at_seconds=0.0,
                frequency_hz=link.band.freq_min_hz,
                transition_type=TransitionType.CHANNEL_SWITCH,
                reason="initial frequency before any scripted change",
                seed_context=None,
            )
        )

    for change in changes:
        at_seconds = change.at_offset.total_seconds()
        if at_seconds >= duration_s:
            break
        events.append(
            RealizedFrequencyEvent(
                link_id=link.id,
                at_seconds=at_seconds,
                frequency_hz=change.frequency_hz,
                transition_type=change.transition_type,
                reason="scripted frequency change",
                seed_context=None,
            )
        )
    return events


def _realize_probabilistic(link: DroneRfLink, duration_s: float) -> list[RealizedFrequencyEvent]:
    behaviour = link.frequency_behaviour
    channels = link.band.allowed_channels_hz
    if not channels or behaviour.mean_dwell_s is None or behaviour.mean_dwell_s <= 0:
        return []
    assert behaviour.random_seed is not None  # enforced by FrequencyBehaviour's own validator

    segments = probabilistic_dwell_segments(
        behaviour.random_seed, behaviour.mean_dwell_s, channels, duration_s
    )
    events: list[RealizedFrequencyEvent] = []
    for start, _end, frequency_hz in segments:
        if start >= duration_s:
            break
        events.append(
            RealizedFrequencyEvent(
                link_id=link.id,
                at_seconds=start,
                frequency_hz=frequency_hz,
                transition_type=TransitionType.CHANNEL_SWITCH,
                reason="probabilistic dwell transition",
                seed_context=behaviour.random_seed,
            )
        )
    return events


def realize_frequency_timeline(
    link: DroneRfLink, duration_s: float
) -> list[RealizedFrequencyEvent]:
    """Deterministic realized frequency-event sequence over [0, duration_s).

    Returns an empty list when the link's mode has nothing deterministic to
    realize (MISSION_TRIGGERED, EXTERNAL_STATE_TRIGGERED, or a
    PROBABILISTIC_ADAPTIVE link missing ``allowed_channels_hz``/
    ``mean_dwell_s``).
    """
    mode = link.frequency_behaviour.mode
    if mode == FrequencySwitchingMode.SCRIPTED:
        return _realize_scripted(link, duration_s)
    if mode == FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE:
        return _realize_probabilistic(link, duration_s)
    return []
