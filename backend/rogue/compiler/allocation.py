"""Physical TX channel allocation for the RF Environment Compiler (M6).

Assigns each ``RfWindow`` span to one of ``capability_profile``'s declared
physical TX channels (rf-model.md section 8: "prefer stable assignments for
intra-band changes; permit migration for band changes"). A span reuses the
same physical channel as the previous span of the same ``window_key`` when
that channel is still free and still tunable to the new center/bandwidth;
otherwise it's a migration to the first free, capable channel (first-fit —
see docs/decisions/ADR-006 for why this is a simplification, not a full
scheduler: no cost-optimal reassignment, no aggregate-power/intermodulation
check across channels).
"""

from __future__ import annotations

from rogue.compiler.models import (
    Allocation,
    CompilerFinding,
    HardwareCapabilityProfile,
    PhysicalTxChannelCapability,
    RfWindow,
)
from rogue.domain.validation import ValidationSeverity

ChannelKey = tuple[str, int]


def _channel_fits(channel: PhysicalTxChannelCapability, window: RfWindow) -> bool:
    if window.bandwidth_hz > channel.max_usable_bandwidth_hz:
        return False
    freq_min = window.center_frequency_hz - window.bandwidth_hz / 2
    freq_max = window.center_frequency_hz + window.bandwidth_hz / 2
    return any(lo <= freq_min and freq_max <= hi for lo, hi in channel.tunable_ranges_hz)


def allocate_physical_channels(
    windows: list[RfWindow], capability_profile: HardwareCapabilityProfile
) -> tuple[list[Allocation], list[CompilerFinding]]:
    findings: list[CompilerFinding] = []
    allocations: list[Allocation] = []

    channels_by_key = {
        (c.device_id, c.channel_index): c for c in capability_profile.channels
    }
    last_assignment: dict[str, ChannelKey] = {}

    for window in sorted(windows, key=lambda w: (w.start_seconds, w.window_key)):
        busy: set[ChannelKey] = {
            (a.device_id, a.channel_index)
            for a in allocations
            if a.start_seconds < window.end_seconds and window.start_seconds < a.end_seconds
        }

        preferred = last_assignment.get(window.window_key)
        chosen: ChannelKey | None = None
        if preferred is not None:
            preferred_channel = channels_by_key.get(preferred)
            if (
                preferred_channel is not None
                and preferred not in busy
                and _channel_fits(preferred_channel, window)
            ):
                chosen = preferred

        is_migration = False
        if chosen is None:
            for channel in capability_profile.channels:
                key = (channel.device_id, channel.channel_index)
                if key in busy or not _channel_fits(channel, window):
                    continue
                chosen = key
                is_migration = preferred is not None
                break

        if chosen is None:
            findings.append(
                CompilerFinding(
                    severity=ValidationSeverity.BLOCKING,
                    code="insufficient_physical_channels",
                    message=(
                        f"no configured physical TX channel can carry window "
                        f"{window.window_key!r} (center={window.center_frequency_hz} Hz, "
                        f"bandwidth={window.bandwidth_hz} Hz) for "
                        f"[{window.start_seconds}, {window.end_seconds})s without a conflict"
                    ),
                    path="$",
                )
            )
            continue

        device_id, channel_index = chosen
        allocations.append(
            Allocation(
                window_key=window.window_key,
                start_seconds=window.start_seconds,
                end_seconds=window.end_seconds,
                device_id=device_id,
                channel_index=channel_index,
                is_migration=is_migration,
            )
        )
        last_assignment[window.window_key] = chosen

    return allocations, findings
