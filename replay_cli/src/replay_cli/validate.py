"""Validator (CLAUDE.md build-order item 2).

`Scenario.model_validate`/`RadioSpec`'s own `model_validator` already
reject bad gain caps and out-of-range center/rate at *construction* time
(pydantic `ValidationError`) — `validate_scenario_file` catches that and
turns each error into an `Issue` rather than re-implementing those checks.
`validate_scenario` covers what schema validation can't see: catalog
lookups, supported datatypes, per-event frequency/bandwidth fit after the
compiler's frequency shift, and timeline+frequency overlap between events.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from replay_cli.schema import Catalog, CatalogError, Event, Recording, Scenario

# The sigmf package (and this tool's compiler) support exactly these —
# matches CLAUDE.md's "support cf32_le, ci16_le, ci8, cu8 at minimum".
SUPPORTED_DATATYPES = frozenset({"cf32_le", "ci16_le", "ci8", "cu8"})


@dataclass(frozen=True)
class Issue:
    level: Literal["warning", "error"]
    where: str
    message: str


def validate_scenario_file(scenario_path: Path, catalog_path: Path) -> list[Issue]:
    """The full `replay validate` pipeline: parse, schema-validate, then
    (only if schema-valid) run the semantic checks below.
    """
    try:
        raw = yaml.safe_load(scenario_path.read_text())
    except yaml.YAMLError as exc:
        return [Issue("error", str(scenario_path), f"invalid YAML: {exc}")]

    try:
        scenario = Scenario.model_validate(raw)
    except ValidationError as exc:
        return [
            Issue("error", ".".join(str(part) for part in err["loc"]), err["msg"])
            for err in exc.errors()
        ]

    catalog = Catalog.load(catalog_path)
    return validate_scenario(scenario, catalog)


def _freq_shift_and_half_span_hz(
    recording: Recording, scenario: Scenario
) -> tuple[float, float] | None:
    """``(shift_hz, half_span_hz)``: how far the recording's own centre sits
    from the radio's tuned centre, and its occupied baseband half-span once
    shifted into the composite — conservative (centre +/- sample_rate/2,
    not the signal's actual bandwidth) per CLAUDE.md's fit-check wording.

    The half-span uses ``min(recording's own sample rate, the radio's
    rate)``, not just the recording's native rate: `compile.py` resamples
    every recording down to the radio's own rate before placing it, which
    band-limits it to the radio's Nyquist regardless of how wide the
    original capture was.
    """
    if recording.center_freq_hz is None or recording.sample_rate_hz is None:
        return None
    shift_hz = recording.center_freq_hz - scenario.radio.center_mhz * 1e6
    half_span_hz = min(recording.sample_rate_hz, scenario.radio.rate_msps * 1e6) / 2
    return (shift_hz, half_span_hz)


def _span_bounds(shift_hz: float, half_span_hz: float) -> tuple[float, float]:
    return (shift_hz - half_span_hz, shift_hz + half_span_hz)


def _spans_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# Back-to-back events (event B's start_s == event A's own start_s + dur_s)
# are the common case for a sequential multi-drone scenario, and
# start_s/dur_s arithmetic on floats doesn't always land exactly on the
# same value it's compared against (0.2 + 0.1 != 0.3) -- without this
# tolerance, adjacent-but-not-overlapping events spuriously trigger the
# overlap warning below. A microsecond is far tighter than this tool's
# own timing precision has any business claiming.
_TIME_EPSILON_S = 1e-6


def _times_overlap(event_a: Event, event_b: Event) -> bool:
    return (
        event_a.start_s < event_b.end_s - _TIME_EPSILON_S
        and event_b.start_s < event_a.end_s - _TIME_EPSILON_S
    )


def validate_scenario(scenario: Scenario, catalog: Catalog) -> list[Issue]:
    issues: list[Issue] = []
    resolved_spans: list[tuple[int, tuple[float, float]]] = []

    for index, event in enumerate(scenario.events):
        where = f"events[{index}] ({event.drone})"
        variant = event.variant
        if variant is None:
            issues.append(Issue("warning", where, event.reason))
            continue

        try:
            recording = catalog.get(event.drone, variant)
        except CatalogError as exc:
            issues.append(Issue("error", where, str(exc)))
            continue

        if recording.datatype not in SUPPORTED_DATATYPES:
            issues.append(
                Issue(
                    "error",
                    where,
                    f"recording datatype {recording.datatype!r} is not one of "
                    f"{sorted(SUPPORTED_DATATYPES)}",
                )
            )
            continue

        shift_and_half_span = _freq_shift_and_half_span_hz(recording, scenario)
        if shift_and_half_span is None:
            issues.append(
                Issue("error", where, "recording has no known centre frequency/sample rate")
            )
            continue
        shift_hz, half_span_hz = shift_and_half_span
        usable_half_hz = scenario.radio.usable_bw_mhz * 1e6 / 2

        # The recording's own centre must be reachable at all -- this is a
        # hard error regardless of bandwidth: no amount of resampling
        # moves where the signal's energy actually sits.
        if abs(shift_hz) > usable_half_hz:
            issues.append(
                Issue(
                    "error",
                    where,
                    f"recording centre is {shift_hz / 1e6:+.3f} MHz from the radio's tuned "
                    f"centre, outside its +/-{usable_half_hz / 1e6:.3f} MHz usable range",
                )
            )
            continue

        span = _span_bounds(shift_hz, half_span_hz)
        # The *conservative* full-sample-rate span exceeding the usable
        # bandwidth is only a warning, not an error: it assumes the
        # recording's entire sample rate is occupied, which is pessimistic
        # for a narrowband signal captured at a high native rate (e.g. the
        # drone corpus's 125 Msps captures) -- the centre is still fine,
        # so the real content may well fit even though this worst case
        # doesn't.
        if max(abs(span[0]), abs(span[1])) > usable_half_hz:
            issues.append(
                Issue(
                    "warning",
                    where,
                    f"recording's conservative span {span[0] / 1e6:.3f}..{span[1] / 1e6:.3f} MHz "
                    f"(assumes the full sample rate is occupied) exceeds the radio's "
                    f"+/-{usable_half_hz / 1e6:.3f} MHz usable bandwidth -- fine if the actual "
                    "signal content is narrower than that",
                )
            )
        resolved_spans.append((index, span))

    for i, (idx_a, span_a) in enumerate(resolved_spans):
        for idx_b, span_b in resolved_spans[i + 1 :]:
            event_a, event_b = scenario.events[idx_a], scenario.events[idx_b]
            if _times_overlap(event_a, event_b) and _spans_overlap(span_a, span_b):
                issues.append(
                    Issue(
                        "warning",
                        f"events[{idx_a}] & events[{idx_b}]",
                        "overlap in time and in frequency span",
                    )
                )

    return issues
