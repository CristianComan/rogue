"""SigMF ``.sigmf-meta`` metadata parsing.

Pure and I/O-free: takes already-fetched metadata bytes and returns a typed,
partially-interpreted result. Implements enough of the SigMF core namespace
(https://github.com/sigmf/SigMF) to derive
``rogue.domain.recording.IQRecording``'s typed fields. Anything not mapped to
one of those typed fields — remaining ``global`` keys, ``captures``,
``annotations``, ``collection`` — is preserved verbatim by the caller in
``extra_sigmf_fields`` rather than dropped, per CLAUDE.md rule 7.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Bytes for one scalar component of a SigMF dataset format string, e.g. the
# "f32" in "cf32_le". Packed sub-byte formats (ci12_le, ...) are not
# supported and are rejected as an unsupported datatype.
_COMPONENT_BYTES = {
    "f64": 8,
    "f32": 4,
    "i32": 4,
    "u32": 4,
    "i16": 2,
    "u16": 2,
    "i8": 1,
    "u8": 1,
}


def bytes_per_sample(datatype: str) -> int | None:
    """Bytes for one (all-components) sample of a SigMF ``core:datatype`` string.

    Returns ``None`` if ``datatype`` is empty or not a supported format.
    """
    body = datatype
    if body.startswith("c"):
        complex_type = True
        body = body[1:]
    elif body.startswith("r"):
        complex_type = False
        body = body[1:]
    else:
        return None

    if body.endswith(("_le", "_be")):
        body = body[:-3]

    component_bytes = _COMPONENT_BYTES.get(body)
    if component_bytes is None:
        return None
    return component_bytes * (2 if complex_type else 1)


@dataclass
class ParsedSigMF:
    """Result of parsing a ``.sigmf-meta`` document."""

    sample_format: str
    sample_rate_hz: float | None
    num_channels: int
    center_frequency_hz: float | None
    declared_sha512: str | None
    extra_fields: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def parse_metadata(raw: bytes) -> ParsedSigMF:
    """Parse ``.sigmf-meta`` JSON bytes.

    Structural/required-field problems are collected into ``errors`` rather
    than raised, so the caller can turn every one of them into a
    ``ValidationFinding`` instead of failing on the first.
    """
    errors: list[str] = []
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return ParsedSigMF(
            sample_format="",
            sample_rate_hz=None,
            num_channels=1,
            center_frequency_hz=None,
            declared_sha512=None,
            errors=[f"invalid JSON: {exc}"],
        )

    global_fields = document.get("global") if isinstance(document, dict) else None
    if not isinstance(global_fields, dict):
        errors.append("missing required 'global' object")
        global_fields = {}

    sample_format_raw = global_fields.get("core:datatype")
    sample_format = sample_format_raw if isinstance(sample_format_raw, str) else ""
    if not sample_format:
        errors.append("missing required 'core:datatype'")
    elif bytes_per_sample(sample_format) is None:
        errors.append(f"unsupported core:datatype {sample_format!r}")

    sample_rate_raw = global_fields.get("core:sample_rate")
    sample_rate_hz = float(sample_rate_raw) if isinstance(sample_rate_raw, int | float) else None
    if sample_rate_hz is None:
        errors.append("missing required 'core:sample_rate'")
    elif sample_rate_hz <= 0:
        errors.append("'core:sample_rate' must be positive")

    num_channels_raw = global_fields.get("core:num_channels", 1)
    num_channels = (
        num_channels_raw if isinstance(num_channels_raw, int) and num_channels_raw > 0 else 1
    )

    center_frequency_hz = None
    captures = document.get("captures") if isinstance(document, dict) else None
    if isinstance(captures, list) and captures and isinstance(captures[0], dict):
        freq = captures[0].get("core:frequency")
        if isinstance(freq, int | float):
            center_frequency_hz = float(freq)

    declared_sha512_raw = global_fields.get("core:sha512")
    declared_sha512 = declared_sha512_raw if isinstance(declared_sha512_raw, str) else None

    consumed_global_keys = {"core:datatype", "core:sample_rate", "core:num_channels"}
    extra_fields: dict[str, Any] = {}
    remaining_global = {k: v for k, v in global_fields.items() if k not in consumed_global_keys}
    if remaining_global:
        extra_fields["global"] = remaining_global
    if isinstance(document, dict):
        for key in ("captures", "annotations", "collection"):
            if key in document:
                extra_fields[key] = document[key]

    return ParsedSigMF(
        sample_format=sample_format,
        sample_rate_hz=sample_rate_hz,
        num_channels=num_channels,
        center_frequency_hz=center_frequency_hz,
        declared_sha512=declared_sha512,
        extra_fields=extra_fields,
        errors=errors,
    )
