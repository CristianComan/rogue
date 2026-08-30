"""Tests for Scenario, ScenarioDraft and the immutability of ScenarioVersion."""

from __future__ import annotations

from datetime import timedelta

import pytest
from factories import (
    drone_mission_kwargs,
    drone_rf_link_kwargs,
    make_scenario,
    make_scenario_version,
    recording_reference,
)
from pydantic import ValidationError

from rogue.domain.mission import DroneMission
from rogue.domain.rf import DroneRfLink, RfEmission
from rogue.domain.scenario import (
    SCENARIO_SCHEMA_VERSION,
    ScenarioDraft,
    derive_recording_references,
)


def test_scenario_defaults() -> None:
    scenario = make_scenario()
    assert scenario.current_version_id is None
    assert scenario.coordinate_system == "EPSG:4326"


def test_scenario_draft_defaults_to_revision_zero() -> None:
    draft = ScenarioDraft(scenario_id=make_scenario().id, author="test-operator")
    assert draft.revision == 0
    assert draft.missions == []


def test_scenario_version_carries_schema_version() -> None:
    version = make_scenario_version()
    assert version.schema_version == SCENARIO_SCHEMA_VERSION


def test_scenario_version_is_immutable() -> None:
    version = make_scenario_version()
    with pytest.raises(ValidationError):
        version.change_note = "attempted mutation"


def test_scenario_version_rejects_unknown_fields() -> None:
    from factories import scenario_version_kwargs

    from rogue.domain.scenario import ScenarioVersion

    with pytest.raises(ValidationError):
        ScenarioVersion(**scenario_version_kwargs(), unexpected_field="nope")


def test_derive_recording_references_empty_missions() -> None:
    assert derive_recording_references([]) == []


def test_derive_recording_references_one_emission() -> None:
    ref = recording_reference()
    mission = DroneMission(**drone_mission_kwargs(recording=ref))

    assert derive_recording_references([mission]) == [ref]


def test_derive_recording_references_silence_emission_contributes_nothing() -> None:
    silent = RfEmission(
        recording=None, start_offset=timedelta(0), duration_override=timedelta(seconds=5)
    )
    link = DroneRfLink(**drone_rf_link_kwargs(emissions=[silent]))
    mission = DroneMission(**drone_mission_kwargs(rf_links=[link]))

    assert derive_recording_references([mission]) == []


def test_derive_recording_references_dedupes_across_links_and_missions() -> None:
    ref = recording_reference()
    link_a = DroneRfLink(**drone_rf_link_kwargs(recording=ref))
    link_b = DroneRfLink(**drone_rf_link_kwargs(recording=ref))
    mission_1 = DroneMission(**drone_mission_kwargs(rf_links=[link_a, link_b]))
    mission_2 = DroneMission(**drone_mission_kwargs(recording=ref))

    assert derive_recording_references([mission_1, mission_2]) == [ref]
