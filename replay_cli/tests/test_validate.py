from pathlib import Path

from replay_cli.schema import (
    Catalog,
    DroneEntry,
    Event,
    RadioSpec,
    RadioType,
    Recording,
    Scenario,
    Side,
)
from replay_cli.validate import validate_scenario, validate_scenario_file

RADIO = RadioSpec(
    type=RadioType.AIRT7311,
    channel=0,
    center_mhz=2440,
    rate_msps=20,
    tx_gain_db=-10,
    max_tx_gain_db=-5,
)


def _scenario(*events: Event) -> Scenario:
    return Scenario(name="t", radio=RADIO, events=list(events))


def _catalog(**drone_variants: dict[str, Recording]) -> Catalog:
    return Catalog(
        drones={name: DroneEntry(variants=variants) for name, variants in drone_variants.items()}
    )


def _recording(**overrides: object) -> Recording:
    kwargs: dict[str, object] = {
        "meta": Path("alpha/drone.sigmf-meta"),
        "datatype": "cf32_le",
        "sample_rate_hz": 20_000.0,
        "center_freq_hz": 2_440e6,
        "duration_s": 10.0,
    }
    kwargs.update(overrides)
    return Recording(**kwargs)


def test_unresolvable_catalog_lookup_is_an_error() -> None:
    scenario = _scenario(Event(drone="nope", near=[Side.DRONE], dur_s=1.0))
    catalog = _catalog(alpha={"drone": _recording()})

    issues = validate_scenario(scenario, catalog)

    assert any(issue.level == "error" and "unknown drone" in issue.message for issue in issues)


def test_unsupported_datatype_is_an_error() -> None:
    scenario = _scenario(Event(drone="alpha", near=[Side.DRONE], dur_s=1.0))
    catalog = _catalog(alpha={"drone": _recording(datatype="pcm16")})

    issues = validate_scenario(scenario, catalog)

    assert any(issue.level == "error" and "datatype" in issue.message for issue in issues)


def test_recording_centre_unreachable_is_an_error() -> None:
    # center_freq_hz far from the radio's 2440 MHz center -> no amount of
    # resampling moves where the signal's energy actually sits, so this
    # is a hard error regardless of bandwidth.
    scenario = _scenario(Event(drone="alpha", near=[Side.DRONE], dur_s=1.0))
    catalog = _catalog(alpha={"drone": _recording(center_freq_hz=5_800e6)})

    issues = validate_scenario(scenario, catalog)

    assert any(issue.level == "error" and "outside its" in issue.message for issue in issues)


def test_conservative_span_exceeding_usable_bandwidth_is_only_a_warning() -> None:
    # Same centre as the radio (no shift -- reachable) and the radio
    # running at the recording's own native 125 Msps (no resampling), but
    # the *conservative* full-sample-rate span still exceeds the
    # AIR7311's 100 MHz-wide TX filter (mirrors the real drone corpus
    # against real hardware) -- the actual signal content may still be
    # narrower than that, so this must not block compiling, unlike an
    # unreachable centre.
    radio_125msps = RadioSpec(
        type=RadioType.AIRT7311,
        channel=0,
        center_mhz=2440,
        rate_msps=125,
        tx_gain_db=-10,
        max_tx_gain_db=-5,
    )
    scenario = Scenario(
        name="t",
        radio=radio_125msps,
        events=[Event(drone="alpha", near=[Side.DRONE], dur_s=1.0)],
    )
    catalog = _catalog(
        alpha={"drone": _recording(center_freq_hz=2_440e6, sample_rate_hz=125_000_000.0)}
    )

    issues = validate_scenario(scenario, catalog)

    assert not any(issue.level == "error" for issue in issues)
    assert any(
        issue.level == "warning" and "conservative span" in issue.message for issue in issues
    )


def test_no_op_event_is_a_warning_not_an_error() -> None:
    scenario = _scenario(Event(drone="alpha", near=[], dur_s=1.0))
    catalog = _catalog(alpha={"drone": _recording()})

    issues = validate_scenario(scenario, catalog)

    assert [i.level for i in issues] == ["warning"]


def test_time_and_frequency_overlapping_events_warn() -> None:
    scenario = _scenario(
        Event(drone="alpha", near=[Side.DRONE], start_s=0.0, dur_s=10.0),
        Event(drone="alpha", near=[Side.CONTROLLER], start_s=5.0, dur_s=10.0),
    )
    catalog = _catalog(
        alpha={
            "drone": _recording(center_freq_hz=2_440e6),
            "controller": _recording(center_freq_hz=2_440e6),
        }
    )

    issues = validate_scenario(scenario, catalog)

    assert any("overlap" in issue.message for issue in issues)


def test_non_overlapping_frequency_does_not_warn_even_if_time_overlaps() -> None:
    scenario = _scenario(
        Event(drone="alpha", near=[Side.DRONE], start_s=0.0, dur_s=10.0),
        Event(drone="alpha", near=[Side.CONTROLLER], start_s=5.0, dur_s=10.0),
    )
    catalog = _catalog(
        alpha={
            # Same radio center (2440 MHz), but recordings captured at
            # frequencies far enough apart that their post-shift spans
            # (+/- 10 kHz each, given a 20 kHz sample rate) don't overlap:
            # drone's span is [-10kHz, 10kHz], controller's shifts by
            # 30 kHz to [20kHz, 40kHz].
            "drone": _recording(center_freq_hz=2_440e6, sample_rate_hz=20_000.0),
            "controller": _recording(center_freq_hz=2_440.03e6, sample_rate_hz=20_000.0),
        }
    )

    issues = validate_scenario(scenario, catalog)

    assert not any("overlap" in issue.message for issue in issues)


def test_back_to_back_events_do_not_spuriously_warn_about_overlap() -> None:
    # 0.2 + 0.1 != 0.3 in float64 -- these three events are meant to be
    # back-to-back (sequential, not simultaneous), the common case for a
    # multi-drone scenario. Without an epsilon tolerance, the second
    # event's end_s (0.2 + 0.1 = 0.30000000000000004) compares as
    # "after" the third event's start_s (0.3 exactly), a false positive.
    scenario = _scenario(
        Event(drone="alpha", near=[Side.DRONE], start_s=0.0, dur_s=0.1),
        Event(drone="alpha", near=[Side.DRONE], start_s=0.1, dur_s=0.1),
        Event(drone="alpha", near=[Side.DRONE], start_s=0.2, dur_s=0.1),
    )
    catalog = _catalog(alpha={"drone": _recording(center_freq_hz=2_440e6)})

    issues = validate_scenario(scenario, catalog)

    assert not any("overlap" in issue.message for issue in issues)


def test_validate_scenario_file_reports_invalid_yaml(tmp_path: Path) -> None:
    scenario_path = tmp_path / "bad.yaml"
    scenario_path.write_text("not: valid: yaml: [")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("{}")

    issues = validate_scenario_file(scenario_path, catalog_path)

    assert len(issues) == 1
    assert issues[0].level == "error"


def test_validate_scenario_file_reports_gain_cap_violation(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
name: t
radio:
  type: airt7311
  center_mhz: 2440
  rate_msps: 20
  tx_gain_db: 0
  max_tx_gain_db: -5
events:
  - drone: alpha
    near: [drone]
    dur_s: 1.0
"""
    )
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("{}")

    issues = validate_scenario_file(scenario_path, catalog_path)

    assert any(issue.level == "error" for issue in issues)
