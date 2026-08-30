"""Tests for RF band/emission/frequency-behaviour/link entities."""

from __future__ import annotations

from datetime import timedelta

import pytest
from factories import drone_rf_link_kwargs, rf_band_kwargs
from pydantic import ValidationError

from rogue.domain.rf import (
    DroneRfLink,
    FrequencyBehaviour,
    FrequencySwitchingMode,
    ResourcePreference,
    RfBand,
    RfEmission,
)


def test_rf_band_rejects_inverted_range() -> None:
    with pytest.raises(ValidationError):
        RfBand(freq_min_hz=2_400_000_000.0, freq_max_hz=2_000_000_000.0)


def test_rf_band_rejects_out_of_range_channel() -> None:
    with pytest.raises(ValidationError):
        RfBand(**rf_band_kwargs(allowed_channels_hz=[9_000_000_000.0]))


def test_scripted_mode_requires_scripted_changes() -> None:
    with pytest.raises(ValidationError):
        FrequencyBehaviour(mode=FrequencySwitchingMode.SCRIPTED, scripted_changes=[])


def test_probabilistic_mode_requires_seed() -> None:
    with pytest.raises(ValidationError):
        FrequencyBehaviour(mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE)


def test_probabilistic_mode_valid_with_seed() -> None:
    behaviour = FrequencyBehaviour(
        mode=FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE, random_seed=42, mean_dwell_s=5.0
    )
    assert behaviour.random_seed == 42


def test_drone_rf_link_requires_at_least_one_emission() -> None:
    with pytest.raises(ValidationError):
        DroneRfLink(**drone_rf_link_kwargs(emissions=[]))


def test_resource_preference_has_no_device_binding_fields() -> None:
    field_names = set(ResourcePreference.model_fields)
    assert not field_names & {"device_serial", "agent_id", "channel_index", "sdr_serial"}


def test_valid_drone_rf_link_round_trips() -> None:
    link = DroneRfLink(**drone_rf_link_kwargs())
    dumped = link.model_dump(mode="json")
    restored = DroneRfLink.model_validate(dumped)
    assert restored.role == link.role
    assert len(restored.emissions) == 1


def test_silence_emission_requires_explicit_duration() -> None:
    with pytest.raises(ValidationError):
        RfEmission(recording=None, start_offset=timedelta(0))


def test_silence_emission_valid_with_duration() -> None:
    emission = RfEmission(
        recording=None, start_offset=timedelta(seconds=5), duration_override=timedelta(seconds=10)
    )
    assert emission.recording is None
    assert emission.duration_override == timedelta(seconds=10)


def test_silence_emission_round_trips() -> None:
    emission = RfEmission(
        recording=None, start_offset=timedelta(0), duration_override=timedelta(seconds=3)
    )
    dumped = emission.model_dump(mode="json")
    restored = RfEmission.model_validate(dumped)
    assert restored.recording is None
