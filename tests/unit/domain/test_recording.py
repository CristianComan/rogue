"""Tests for IQRecording and RecordingReference."""

from __future__ import annotations

import pytest
from factories import make_iq_recording
from pydantic import ValidationError


def test_make_iq_recording_reference_matches_source() -> None:
    recording = make_iq_recording()
    ref = recording.reference()

    assert ref.recording_id == recording.id
    assert ref.version == recording.version


def test_sha256_must_be_64_hex_chars() -> None:
    with pytest.raises(ValidationError):
        make_iq_recording(sha256_data="not-a-hash")


def test_unknown_sigmf_extension_fields_are_retained() -> None:
    recording = make_iq_recording(extra_sigmf_fields={"vendor:custom_field": 42})
    assert recording.extra_sigmf_fields == {"vendor:custom_field": 42}


def test_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_iq_recording(version=0)
