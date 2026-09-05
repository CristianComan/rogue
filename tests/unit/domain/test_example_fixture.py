"""Loads the example scenario fixture to prove the portable YAML representation
is a valid, round-trippable ScenarioVersion (domain-model.md section 7)."""

from __future__ import annotations

from pathlib import Path

from rogue.domain.scenario import ScenarioVersion
from rogue.domain.serialization import from_yaml, to_yaml
from rogue.domain.validation import ValidationSeverity, validate_scenario_version

FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "examples" / "scenarios" / "single-drone-orbit.yaml"
)


def test_example_fixture_loads_as_valid_scenario_version() -> None:
    version = from_yaml(ScenarioVersion, FIXTURE_PATH.read_text())

    assert version.version_number == 1
    assert len(version.missions) == 1
    assert version.missions[0].trajectory.template.value == "orbit"


def test_example_fixture_has_no_blocking_validation_findings() -> None:
    version = from_yaml(ScenarioVersion, FIXTURE_PATH.read_text())

    findings = validate_scenario_version(version)

    assert all(f.severity != ValidationSeverity.BLOCKING for f in findings)


def test_example_fixture_round_trips_through_yaml() -> None:
    version = from_yaml(ScenarioVersion, FIXTURE_PATH.read_text())

    restored = from_yaml(ScenarioVersion, to_yaml(version))

    assert restored == version
