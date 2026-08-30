"""Tests for build_ingest_candidate, with object_store monkeypatched.

No real S3/MinIO is used here — per CLAUDE.md's "tests default to
simulation" safety rule, these exercise validation logic against canned
metadata/data bytes instead.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

import pytest

from rogue.catalogue import ingest as ingest_module
from rogue.domain.recording import AccessClassification
from rogue.domain.validation import ValidationSeverity
from rogue.storage import object_store
from rogue.storage.object_store import ObjectDigest, ObjectNotFoundError

METADATA_KEY = "recordings/example.sigmf-meta"
DATA_KEY = "recordings/example.sigmf-data"


def _metadata_bytes(**global_overrides: object) -> bytes:
    document = {
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": 1_000_000.0,
            **global_overrides,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": 2_450_000_000.0}],
    }
    return json.dumps(document).encode()


def _digest(data: bytes) -> ObjectDigest:
    return ObjectDigest(
        sha256=hashlib.sha256(data).hexdigest(),
        sha512=hashlib.sha512(data).hexdigest(),
        size_bytes=len(data),
    )


def _patch_store(monkeypatch: pytest.MonkeyPatch, *, metadata: bytes, data: bytes) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: metadata)
    monkeypatch.setattr(object_store, "digest_object", lambda key: _digest(data))


def _base_kwargs(**overrides: object) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "recording_id": None,
        "version": 1,
        "metadata_object_key": METADATA_KEY,
        "data_object_key": DATA_KEY,
        "provenance": "lab-capture",
        "access_classification": AccessClassification.RESTRICTED,
        "allowed_use_constraints": [],
        "allowed_frequency_min_hz": None,
        "allowed_frequency_max_hz": None,
    }
    kwargs.update(overrides)
    return kwargs


def test_valid_recording_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    data = b"\x00" * 800  # 100 complex-float32 samples
    _patch_store(monkeypatch, metadata=_metadata_bytes(), data=data)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is not None
    assert not any(f.severity == ValidationSeverity.BLOCKING for f in findings)
    assert candidate.sample_count == 100
    assert candidate.duration_s == pytest.approx(0.0001)
    assert candidate.sample_rate_hz == 1_000_000.0
    assert candidate.center_frequency_hz == 2_450_000_000.0
    assert candidate.sha256_data == hashlib.sha256(data).hexdigest()
    assert candidate.sha256_metadata == hashlib.sha256(_metadata_bytes()).hexdigest()


def test_missing_metadata_object_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(key: str) -> bytes:
        raise ObjectNotFoundError(key)

    monkeypatch.setattr(object_store, "get_object_bytes", _raise)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is None
    assert any(f.code == "sigmf_metadata_object_missing" for f in findings)


def test_missing_data_object_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: _metadata_bytes())

    def _raise(key: str) -> ObjectDigest:
        raise ObjectNotFoundError(key)

    monkeypatch.setattr(object_store, "digest_object", _raise)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is None
    assert any(f.code == "sigmf_data_object_missing" for f in findings)


def test_invalid_metadata_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(monkeypatch, metadata=b"not json", data=b"\x00" * 8)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is None
    assert any(f.code == "sigmf_metadata_invalid" for f in findings)


def test_data_length_not_multiple_of_sample_size_is_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_store(monkeypatch, metadata=_metadata_bytes(), data=b"\x00" * 7)  # cf32 = 8 bytes/sample

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is None
    assert any(f.code == "sigmf_data_length_mismatch" for f in findings)


def test_checksum_mismatch_against_declared_sha512_is_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = b"\x00" * 8
    metadata = _metadata_bytes(**{"core:sha512": "deadbeef"})
    _patch_store(monkeypatch, metadata=metadata, data=data)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is None
    assert any(f.code == "sigmf_checksum_mismatch" for f in findings)


def test_checksum_matching_declared_sha512_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    data = b"\x00" * 8
    metadata = _metadata_bytes(**{"core:sha512": hashlib.sha512(data).hexdigest()})
    _patch_store(monkeypatch, metadata=metadata, data=data)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is not None
    assert not any(f.code == "sigmf_checksum_mismatch" for f in findings)


def test_missing_center_frequency_is_warning_not_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = json.dumps(
        {"global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000.0}}
    ).encode()
    data = b"\x00" * 8
    _patch_store(monkeypatch, metadata=metadata, data=data)

    candidate, findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is not None
    warning = next(f for f in findings if f.code == "sigmf_missing_center_frequency")
    assert warning.severity == ValidationSeverity.WARNING


def test_invalid_allowed_frequency_range_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(monkeypatch, metadata=_metadata_bytes(), data=b"\x00" * 8)

    candidate, findings = ingest_module.build_ingest_candidate(
        **_base_kwargs(allowed_frequency_min_hz=6e9, allowed_frequency_max_hz=1e9)
    )

    assert candidate is None
    assert any(f.code == "invalid_allowed_frequency_range" for f in findings)


def test_extra_sigmf_fields_are_preserved_on_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata_bytes(**{"vendor:custom_field": 7})
    _patch_store(monkeypatch, metadata=metadata, data=b"\x00" * 8)

    candidate, _findings = ingest_module.build_ingest_candidate(**_base_kwargs())

    assert candidate is not None
    assert candidate.extra_sigmf_fields["global"]["vendor:custom_field"] == 7


def test_explicit_recording_id_and_version_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(monkeypatch, metadata=_metadata_bytes(), data=b"\x00" * 8)
    fixed_id = uuid4()

    candidate, _findings = ingest_module.build_ingest_candidate(
        **_base_kwargs(recording_id=fixed_id, version=3)
    )

    assert candidate is not None
    assert candidate.id == fixed_id
    assert candidate.version == 3
