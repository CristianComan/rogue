"""JSON/YAML round-trip tests for a full ScenarioVersion (M1 exit criterion)."""

from __future__ import annotations

from factories import make_scenario_version

from rogue.domain.scenario import ScenarioVersion
from rogue.domain.serialization import from_json, from_yaml, to_json, to_yaml


def test_scenario_version_json_round_trip() -> None:
    version = make_scenario_version()

    restored = from_json(ScenarioVersion, to_json(version))

    assert restored == version


def test_scenario_version_yaml_round_trip() -> None:
    version = make_scenario_version()

    restored = from_yaml(ScenarioVersion, to_yaml(version))

    assert restored == version


def test_yaml_output_is_human_readable_text() -> None:
    version = make_scenario_version()
    text = to_yaml(version)

    assert "schema_version:" in text
    assert "missions:" in text
