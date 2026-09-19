"""Tests for the pure SigMF ``.sigmf-meta`` parser."""

from __future__ import annotations

import json

from rogue.catalogue.sigmf import bytes_per_sample, parse_metadata


def _meta_bytes(**global_overrides: object) -> bytes:
    document = {
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": 1_000_000.0,
            "core:version": "1.0.0",
            **global_overrides,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": 2_450_000_000.0}],
        "annotations": [],
    }
    return json.dumps(document).encode()


def test_bytes_per_sample_complex_float32() -> None:
    assert bytes_per_sample("cf32_le") == 8


def test_bytes_per_sample_real_int16() -> None:
    assert bytes_per_sample("ri16_be") == 2


def test_bytes_per_sample_complex_u8_no_endianness_suffix() -> None:
    assert bytes_per_sample("cu8") == 2


def test_bytes_per_sample_unsupported_prefix_returns_none() -> None:
    assert bytes_per_sample("xf32_le") is None


def test_bytes_per_sample_unsupported_component_returns_none() -> None:
    assert bytes_per_sample("ci12_le") is None


def test_bytes_per_sample_empty_string_returns_none() -> None:
    assert bytes_per_sample("") is None


def test_parse_metadata_happy_path() -> None:
    parsed = parse_metadata(_meta_bytes())

    assert parsed.errors == []
    assert parsed.sample_format == "cf32_le"
    assert parsed.sample_rate_hz == 1_000_000.0
    assert parsed.num_channels == 1
    assert parsed.center_frequency_hz == 2_450_000_000.0


def test_parse_metadata_invalid_json_reports_single_error() -> None:
    parsed = parse_metadata(b"not json")

    assert len(parsed.errors) == 1
    assert "invalid JSON" in parsed.errors[0]


def test_parse_metadata_missing_global_object() -> None:
    parsed = parse_metadata(json.dumps({}).encode())

    assert "missing required 'global' object" in parsed.errors


def test_parse_metadata_missing_datatype() -> None:
    document = {"global": {"core:sample_rate": 1_000_000.0}}
    parsed = parse_metadata(json.dumps(document).encode())

    assert "missing required 'core:datatype'" in parsed.errors


def test_parse_metadata_unsupported_datatype() -> None:
    parsed = parse_metadata(_meta_bytes(**{"core:datatype": "ci12_le"}))

    assert any("unsupported core:datatype" in e for e in parsed.errors)


def test_parse_metadata_missing_sample_rate() -> None:
    document = {"global": {"core:datatype": "cf32_le"}}
    parsed = parse_metadata(json.dumps(document).encode())

    assert "missing required 'core:sample_rate'" in parsed.errors


def test_parse_metadata_negative_sample_rate() -> None:
    parsed = parse_metadata(_meta_bytes(**{"core:sample_rate": -1.0}))

    assert "'core:sample_rate' must be positive" in parsed.errors


def test_parse_metadata_no_captures_leaves_frequency_none() -> None:
    document = {
        "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000.0},
    }
    parsed = parse_metadata(json.dumps(document).encode())

    assert parsed.center_frequency_hz is None


def test_parse_metadata_num_channels_defaults_to_one() -> None:
    parsed = parse_metadata(_meta_bytes())

    assert parsed.num_channels == 1


def test_parse_metadata_respects_num_channels() -> None:
    parsed = parse_metadata(_meta_bytes(**{"core:num_channels": 4}))

    assert parsed.num_channels == 4


def test_parse_metadata_declared_sha512_extracted() -> None:
    parsed = parse_metadata(_meta_bytes(**{"core:sha512": "abc123"}))

    assert parsed.declared_sha512 == "abc123"


def test_parse_metadata_preserves_unknown_global_and_captures_in_extra_fields() -> None:
    parsed = parse_metadata(_meta_bytes(**{"vendor:custom_field": 42}))

    assert parsed.extra_fields["global"] == {
        "core:version": "1.0.0",
        "vendor:custom_field": 42,
    }
    assert parsed.extra_fields["captures"] == [
        {"core:sample_start": 0, "core:frequency": 2_450_000_000.0}
    ]
    assert parsed.extra_fields["annotations"] == []
