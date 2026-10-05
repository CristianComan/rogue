from pathlib import Path

import pytest
from pydantic import ValidationError

from replay_cli.schema import (
    Catalog,
    CatalogError,
    Scenario,
    Side,
    Variant,
    resolve_events,
    resolve_variant,
)

ROOT = Path(__file__).resolve().parents[1]


def test_rule_table():
    assert resolve_variant([Side.DRONE]) == Variant.DRONE
    assert resolve_variant([Side.CONTROLLER]) == Variant.CONTROLLER
    assert resolve_variant([Side.DRONE, Side.CONTROLLER]) == Variant.BOTH
    assert resolve_variant([]) is None


def test_example_scenario_resolves():
    sc = Scenario.load(ROOT / "scenarios/example_mixed.yaml")
    cat = Catalog.load(ROOT / "catalog/drones.example.yaml")
    res = resolve_events(sc, cat)
    assert [r.variant for r in res] == [Variant.DRONE, Variant.BOTH, Variant.CONTROLLER]
    assert sc.duration_s == 120


def test_noop_event_is_skipped():
    sc = Scenario.load(ROOT / "scenarios/example_mixed.yaml")
    sc.events[0].near = []
    cat = Catalog.load(ROOT / "catalog/drones.example.yaml")
    assert resolve_events(sc, cat)[0].skipped


def test_gain_above_cap_rejected():
    sc = Scenario.load(ROOT / "scenarios/example_mixed.yaml").model_dump(mode="json")
    sc["radio"]["tx_gain_db"] = 0
    with pytest.raises(ValidationError):
        Scenario.model_validate(sc)


def test_rate_over_radio_limit_rejected():
    sc = Scenario.load(ROOT / "scenarios/example_mixed.yaml").model_dump(mode="json")
    sc["radio"]["rate_msps"] = 200
    with pytest.raises(ValidationError):
        Scenario.model_validate(sc)


def test_unknown_drone():
    sc = Scenario.load(ROOT / "scenarios/example_mixed.yaml")
    sc.events[0].drone = "nope"
    cat = Catalog.load(ROOT / "catalog/drones.example.yaml")
    with pytest.raises(CatalogError):
        resolve_events(sc, cat)


def test_x440_cannot_do_5g8():
    sc = Scenario.load(ROOT / "scenarios/example_mixed.yaml").model_dump(mode="json")
    sc["radio"]["type"] = "x440"
    sc["radio"]["center_mhz"] = 5800
    with pytest.raises(ValidationError):
        Scenario.model_validate(sc)
