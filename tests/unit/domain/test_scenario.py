"""Tests for Scenario, ScenarioDraft and the immutability of ScenarioVersion."""

from __future__ import annotations

import pytest
from factories import make_scenario, make_scenario_version
from pydantic import ValidationError

from rogue.domain.scenario import SCENARIO_SCHEMA_VERSION, ScenarioDraft


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
