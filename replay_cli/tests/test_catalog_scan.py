from pathlib import Path

from conftest import write_sigmf_tone
from replay_cli.catalog_scan import scan_recordings, scan_rogue_corpus, write_catalog
from replay_cli.schema import Catalog, Variant


def test_scan_finds_all_variants(tmp_path: Path) -> None:
    drone_dir = tmp_path / "recordings" / "alpha"
    write_sigmf_tone(
        drone_dir / "drone", sample_rate_hz=20_000.0, center_freq_hz=2_440e6, duration_s=0.5
    )
    write_sigmf_tone(
        drone_dir / "controller", sample_rate_hz=20_000.0, center_freq_hz=5_800e6, duration_s=0.5
    )
    write_sigmf_tone(
        drone_dir / "both", sample_rate_hz=20_000.0, center_freq_hz=2_440e6, duration_s=0.5
    )

    result = scan_recordings(tmp_path / "recordings")

    assert "alpha" in result.catalog.drones
    entry = result.catalog.drones["alpha"]
    assert set(entry.variants) == {Variant.DRONE, Variant.CONTROLLER, Variant.BOTH}
    drone_rec = entry.variants[Variant.DRONE]
    assert drone_rec.datatype == "cf32_le"
    assert drone_rec.sample_rate_hz == 20_000.0
    assert drone_rec.center_freq_hz == 2_440e6
    assert drone_rec.duration_s == 0.5
    assert not [w for w in result.warnings if "missing" in w.message]


def test_scan_warns_on_missing_variant(tmp_path: Path) -> None:
    drone_dir = tmp_path / "recordings" / "alpha"
    write_sigmf_tone(drone_dir / "drone")

    result = scan_recordings(tmp_path / "recordings")

    assert Variant.DRONE in result.catalog.drones["alpha"].variants
    assert any("missing 'controller'" in w.message for w in result.warnings)
    assert any("missing 'both'" in w.message for w in result.warnings)


def test_scan_warns_on_unrecognized_file_and_skips_it(tmp_path: Path) -> None:
    drone_dir = tmp_path / "recordings" / "alpha"
    write_sigmf_tone(drone_dir / "drone")
    write_sigmf_tone(drone_dir / "mystery_variant")

    result = scan_recordings(tmp_path / "recordings")

    assert len(result.catalog.drones["alpha"].variants) == 1
    assert any("unrecognized variant file stem" in w.message for w in result.warnings)


def test_scan_skips_drone_dir_with_no_recognized_recordings(tmp_path: Path) -> None:
    empty_dir = tmp_path / "recordings" / "nothing_here"
    empty_dir.mkdir(parents=True)

    result = scan_recordings(tmp_path / "recordings")

    assert "nothing_here" not in result.catalog.drones
    assert any("drone skipped" in w.message for w in result.warnings)


def test_rogue_corpus_maps_experiment_scenario_to_variant(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    write_sigmf_tone(
        corpus_dir / "01" / "drone=01_exp=air_fc=2450e6_fs=125e6_fnum=0", experiment_scenario="air"
    )
    write_sigmf_tone(
        corpus_dir / "01" / "drone=01_exp=both_fc=5800e6_fs=125e6_fnum=0",
        experiment_scenario="both",
    )

    result = scan_rogue_corpus(corpus_dir)

    entry = result.catalog.drones["01"]
    assert set(entry.variants) == {Variant.DRONE, Variant.BOTH}
    assert any("missing 'controller'" in w.message for w in result.warnings)


def test_rogue_corpus_skips_no_drone_baseline(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    write_sigmf_tone(
        corpus_dir / "no_drone" / "drone=none_exp=env_fc=2450e6_fs=125e6_fnum=0",
        experiment_scenario="env",
    )

    result = scan_rogue_corpus(corpus_dir)

    assert "no_drone" not in result.catalog.drones
    assert not result.warnings  # skipped outright, not even an "unmapped" warning


def test_rogue_corpus_warns_on_unmapped_experiment_scenario(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    write_sigmf_tone(
        corpus_dir / "01" / "drone=01_exp=weird_fc=2450e6_fs=125e6_fnum=0",
        experiment_scenario="weird",
    )

    result = scan_rogue_corpus(corpus_dir)

    assert "01" not in result.catalog.drones
    assert any("doesn't map to a known variant" in w.message for w in result.warnings)


def test_rogue_corpus_keeps_first_and_warns_on_duplicate_variant(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    write_sigmf_tone(
        corpus_dir / "01" / "drone=01_exp=air_fc=2450e6_fs=125e6_fnum=0", experiment_scenario="air"
    )
    write_sigmf_tone(
        corpus_dir / "01" / "drone=01_exp=los_fc=2450e6_fs=125e6_fnum=0", experiment_scenario="los"
    )

    result = scan_rogue_corpus(corpus_dir)

    assert len(result.catalog.drones["01"].variants) == 1
    assert any("already chosen" in w.message for w in result.warnings)


def test_write_catalog_round_trips(tmp_path: Path) -> None:
    drone_dir = tmp_path / "recordings" / "alpha"
    write_sigmf_tone(drone_dir / "drone")
    result = scan_recordings(tmp_path / "recordings")
    out_path = tmp_path / "catalog" / "drones.yaml"

    write_catalog(result.catalog, out_path)
    loaded = Catalog.load(out_path)

    assert loaded.get("alpha", Variant.DRONE).datatype == "cf32_le"
