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

Coherent groups (ADR-012): windows sharing one non-null
``coherent_group_id`` at the same time span (see
``rogue.compiler.coherent_groups``/``windows.py``, which guarantee such
windows are never merged into one) are allocated as one atomic unit — every
member gets a distinct free channel together, or none of them do. This is
the one place this module departs from the plain per-window loop above;
independent (non-coherent) windows are entirely unaffected and allocate
exactly as before.
"""

from __future__ import annotations

from uuid import UUID

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


def _coherent_group_id(window: RfWindow) -> UUID | None:
    """The non-null coherent_group_id shared by this window's channels, if any.

    A coherent-group window always has exactly one CompositeChannel (one
    per target Receiver element — see windows.py's expansion step), so
    checking the first entry is sufficient.
    """
    if not window.channels:
        return None
    return window.channels[0].coherent_group_id


def _busy_channels(allocations: list[Allocation], window: RfWindow) -> set[ChannelKey]:
    return {
        (a.device_id, a.channel_index)
        for a in allocations
        if a.start_seconds < window.end_seconds and window.start_seconds < a.end_seconds
    }


def _choose_channel(
    window: RfWindow,
    capability_profile: HardwareCapabilityProfile,
    channels_by_key: dict[ChannelKey, PhysicalTxChannelCapability],
    busy: set[ChannelKey],
    preferred: ChannelKey | None,
) -> tuple[ChannelKey | None, bool]:
    """(chosen, is_migration) — first-fit, preferring `preferred` when it still fits."""
    if preferred is not None:
        preferred_channel = channels_by_key.get(preferred)
        if (
            preferred_channel is not None
            and preferred not in busy
            and _channel_fits(preferred_channel, window)
        ):
            return preferred, False

    for channel in capability_profile.channels:
        key = (channel.device_id, channel.channel_index)
        if key in busy or not _channel_fits(channel, window):
            continue
        return key, preferred is not None

    return None, False


def _allocate_independent_window(
    window: RfWindow,
    capability_profile: HardwareCapabilityProfile,
    channels_by_key: dict[ChannelKey, PhysicalTxChannelCapability],
    allocations: list[Allocation],
    last_assignment: dict[str, ChannelKey],
    findings: list[CompilerFinding],
) -> None:
    busy = _busy_channels(allocations, window)
    preferred = last_assignment.get(window.window_key)
    chosen, is_migration = _choose_channel(
        window, capability_profile, channels_by_key, busy, preferred
    )

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
        return

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


def _allocate_coherent_unit(
    unit_windows: list[RfWindow],
    capability_profile: HardwareCapabilityProfile,
    channels_by_key: dict[ChannelKey, PhysicalTxChannelCapability],
    allocations: list[Allocation],
    last_assignment: dict[str, ChannelKey],
    findings: list[CompilerFinding],
) -> None:
    """All-or-nothing: every member gets a distinct free channel, or none do.

    Tries each member in turn against a shared `busy` set that also grows
    with this attempt's own tentative picks (so two members never land on
    the same channel), but never mutates `allocations`/`last_assignment`
    until every member has succeeded.
    """
    group_id = _coherent_group_id(unit_windows[0])
    busy = _busy_channels(allocations, unit_windows[0])  # every member shares this span
    tentative: list[tuple[RfWindow, ChannelKey, bool]] = []

    for window in unit_windows:
        preferred = last_assignment.get(window.window_key)
        already_chosen_in_group = {chosen for _w, chosen, _m in tentative}
        chosen, is_migration = _choose_channel(
            window, capability_profile, channels_by_key, busy | already_chosen_in_group, preferred
        )
        if chosen is None:
            findings.append(
                CompilerFinding(
                    severity=ValidationSeverity.BLOCKING,
                    code="insufficient_physical_channels_for_coherent_group",
                    message=(
                        f"coherent group {group_id} needs {len(unit_windows)} simultaneous "
                        f"distinct physical TX channels for [{unit_windows[0].start_seconds}, "
                        f"{unit_windows[0].end_seconds})s but not enough are free/capable — "
                        "no member of this group is allocated for this span (atomic, not partial)"
                    ),
                    path="$",
                )
            )
            return  # atomic: bail without allocating any member
        tentative.append((window, chosen, is_migration))

    for window, chosen, is_migration in tentative:
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


def allocate_physical_channels(
    windows: list[RfWindow], capability_profile: HardwareCapabilityProfile
) -> tuple[list[Allocation], list[CompilerFinding]]:
    findings: list[CompilerFinding] = []
    allocations: list[Allocation] = []
    channels_by_key = {(c.device_id, c.channel_index): c for c in capability_profile.channels}
    last_assignment: dict[str, ChannelKey] = {}

    sorted_windows = sorted(windows, key=lambda w: (w.start_seconds, w.window_key))

    coherent_groups: dict[tuple[float, float, UUID], list[RfWindow]] = {}
    independent: list[RfWindow] = []
    for window in sorted_windows:
        group_id = _coherent_group_id(window)
        if group_id is not None:
            coherent_groups.setdefault(
                (window.start_seconds, window.end_seconds, group_id), []
            ).append(window)
        else:
            independent.append(window)

    # Process every unit (an independent window, or a coherent group) in
    # the same global start-time order the original per-window loop used,
    # so a scenario with no coherent groups allocates identically to before.
    units: list[tuple[float, str, list[RfWindow]]] = [
        (w.start_seconds, w.window_key, [w]) for w in independent
    ]
    for (start, _end, group_id), members in coherent_groups.items():
        units.append((start, f"__coherent_group__:{group_id}", members))
    units.sort(key=lambda u: (u[0], u[1]))

    for _start, _key, unit_windows in units:
        if len(unit_windows) == 1:
            _allocate_independent_window(
                unit_windows[0],
                capability_profile,
                channels_by_key,
                allocations,
                last_assignment,
                findings,
            )
        else:
            _allocate_coherent_unit(
                unit_windows,
                capability_profile,
                channels_by_key,
                allocations,
                last_assignment,
                findings,
            )

    return allocations, findings
