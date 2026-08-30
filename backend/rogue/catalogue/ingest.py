"""Build a validated, not-yet-persisted ``IQRecording`` from S3 object keys.

Mirrors ``rogue.persistence.repository``'s draft-publish shape: fetch and
parse, collect ``ValidationFinding``s, and only return a candidate when there
are no BLOCKING findings — the M4 exit criterion is "validated immutable
recording assets", so ingest must reject before anything is persisted rather
than repair or silently drop bad metadata.

Checks performed (docs/architecture/verification-validation.md §3's "SigMF
pairing, checksum, duration and metadata"):
- metadata/data objects exist and are readable;
- metadata is valid SigMF core JSON (datatype, sample rate);
- the data object's byte length is a whole multiple of the sample size
  implied by ``core:datatype``/``core:num_channels`` (pairing/duration);
- if metadata declares ``core:sha512``, it matches the data object's
  computed SHA-512 (checksum).
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from rogue.catalogue.sigmf import bytes_per_sample, parse_metadata
from rogue.domain.recording import AccessClassification, IQRecording
from rogue.domain.validation import ValidationFinding, ValidationSeverity
from rogue.storage import object_store


def _finding(
    severity: ValidationSeverity, code: str, message: str, path: str = "$"
) -> ValidationFinding:
    return ValidationFinding(severity=severity, code=code, message=message, path=path)


def build_ingest_candidate(
    *,
    recording_id: UUID | None,
    version: int,
    metadata_object_key: str,
    data_object_key: str,
    provenance: str | None,
    access_classification: AccessClassification,
    allowed_use_constraints: list[str],
    allowed_frequency_min_hz: float | None,
    allowed_frequency_max_hz: float | None,
) -> tuple[IQRecording | None, list[ValidationFinding]]:
    """Fetch, parse and validate a SigMF asset pair.

    Returns ``(None, findings)`` when any finding is BLOCKING (nothing is
    fetched further once the objects themselves can't be read), otherwise
    ``(candidate, findings)`` where ``findings`` may still contain WARNINGs.
    Performs synchronous network I/O — callers on the async request path
    must run this via ``asyncio.to_thread``.
    """
    findings: list[ValidationFinding] = []

    if (
        allowed_frequency_min_hz is not None
        and allowed_frequency_max_hz is not None
        and allowed_frequency_min_hz > allowed_frequency_max_hz
    ):
        findings.append(
            _finding(
                ValidationSeverity.BLOCKING,
                "invalid_allowed_frequency_range",
                "allowed_frequency_min_hz exceeds allowed_frequency_max_hz",
                "allowed_frequency_min_hz",
            )
        )

    try:
        metadata_bytes = object_store.get_object_bytes(metadata_object_key)
    except object_store.ObjectNotFoundError:
        findings.append(
            _finding(
                ValidationSeverity.BLOCKING,
                "sigmf_metadata_object_missing",
                f"metadata object {metadata_object_key!r} does not exist",
                "metadata_object_key",
            )
        )
        return None, findings

    try:
        data_digest = object_store.digest_object(data_object_key)
    except object_store.ObjectNotFoundError:
        findings.append(
            _finding(
                ValidationSeverity.BLOCKING,
                "sigmf_data_object_missing",
                f"data object {data_object_key!r} does not exist",
                "data_object_key",
            )
        )
        return None, findings

    parsed = parse_metadata(metadata_bytes)
    for error in parsed.errors:
        findings.append(
            _finding(
                ValidationSeverity.BLOCKING, "sigmf_metadata_invalid", error, "metadata_object_key"
            )
        )

    if parsed.declared_sha512 is not None and parsed.declared_sha512.lower() != data_digest.sha512:
        findings.append(
            _finding(
                ValidationSeverity.BLOCKING,
                "sigmf_checksum_mismatch",
                "computed SHA-512 of the data object does not match metadata's core:sha512",
                "data_object_key",
            )
        )

    if parsed.center_frequency_hz is None:
        findings.append(
            _finding(
                ValidationSeverity.WARNING,
                "sigmf_missing_center_frequency",
                "no captures[0]['core:frequency'] present in SigMF metadata",
                "metadata_object_key",
            )
        )

    sample_count = 0
    duration_s = 0.0
    if not parsed.errors:
        # No metadata errors means sample_format/sample_rate_hz passed
        # parse_metadata's own required-field checks and are usable here.
        assert parsed.sample_rate_hz is not None
        per_sample = bytes_per_sample(parsed.sample_format)
        assert per_sample is not None
        total_per_vector_sample = per_sample * parsed.num_channels
        if data_digest.size_bytes % total_per_vector_sample != 0:
            findings.append(
                _finding(
                    ValidationSeverity.BLOCKING,
                    "sigmf_data_length_mismatch",
                    "data object byte length is not a whole multiple of the sample size implied "
                    "by core:datatype/core:num_channels",
                    "data_object_key",
                )
            )
        else:
            sample_count = data_digest.size_bytes // total_per_vector_sample
            duration_s = sample_count / parsed.sample_rate_hz

    if any(f.severity == ValidationSeverity.BLOCKING for f in findings):
        return None, findings

    assert parsed.sample_rate_hz is not None  # guaranteed: no BLOCKING findings above
    candidate = IQRecording(
        id=recording_id if recording_id is not None else uuid4(),
        version=version,
        metadata_object_key=metadata_object_key,
        data_object_key=data_object_key,
        sha256_metadata=hashlib.sha256(metadata_bytes).hexdigest(),
        sha256_data=data_digest.sha256,
        sample_format=parsed.sample_format,
        sample_rate_hz=parsed.sample_rate_hz,
        sample_count=sample_count,
        duration_s=duration_s,
        center_frequency_hz=parsed.center_frequency_hz,
        provenance=provenance,
        access_classification=access_classification,
        allowed_use_constraints=allowed_use_constraints,
        allowed_frequency_min_hz=allowed_frequency_min_hz,
        allowed_frequency_max_hz=allowed_frequency_max_hz,
        extra_sigmf_fields=parsed.extra_fields,
    )
    return candidate, findings
