"""Catalog scanner (CLAUDE.md build-order item 1).

Two layouts:

- `scan_recordings` — the simple convention (not specified by CLAUDE.md,
  picked here and documented): one subdirectory per drone under
  `rec_dir`, one `<variant>.sigmf-meta` file per `drone`/`controller`/
  `both` variant inside it, e.g. ``<rec_dir>/mavic3/drone.sigmf-meta``.
- `scan_rogue_corpus` — reuses the real local drone-RF corpus already on
  disk for the main ROGUE repo's own M4 catalogue ingest
  (`scripts/ingest_drone_corpus.py`, e.g. `recordings/drone-corpus/
  15June2022/`): one subdirectory per `classification:drone_id` (plus
  the `no_drone` ambient baseline, always skipped — it's a background
  capture, not a per-drone variant), variant read from each recording's
  own `experiment:scenario` SigMF field rather than its filename.

Either way, a subdirectory missing a variant, or a file that can't be
mapped to one, is a scan **warning**, never an error (CLAUDE.md:
"Missing variants are warnings, not errors").

Per-recording metadata (datatype/sample rate/center frequency/duration)
is read via the `sigmf` package rather than hand-parsed, matching
`replay_cli`'s independence from `rogue.catalogue.sigmf`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sigmf.sigmffile import fromfile

from replay_cli.schema import Catalog, DroneEntry, Recording, Variant


@dataclass(frozen=True)
class ScanWarning:
    where: str
    message: str


@dataclass(frozen=True)
class ScanResult:
    catalog: Catalog
    warnings: list[ScanWarning]


def scan_recordings(rec_dir: Path) -> ScanResult:
    warnings: list[ScanWarning] = []
    drones: dict[str, DroneEntry] = {}

    for drone_dir in sorted(p for p in rec_dir.iterdir() if p.is_dir()):
        variants: dict[Variant, Recording] = {}
        for meta_path in sorted(drone_dir.glob("*.sigmf-meta")):
            try:
                variant = Variant(meta_path.stem)
            except ValueError:
                warnings.append(
                    ScanWarning(
                        str(meta_path),
                        f"unrecognized variant file stem {meta_path.stem!r}, skipped",
                    )
                )
                continue
            variants[variant] = _build_recording(meta_path, warnings)

        entry = _finalize_drone(drone_dir.name, variants, warnings)
        if entry is not None:
            drones[drone_dir.name] = entry

    return ScanResult(catalog=Catalog(drones=drones), warnings=warnings)


# ROGUE's own drone-RF corpus (`scripts/ingest_drone_corpus.py`'s source
# layout) uses `experiment:scenario` values that don't line up 1:1 with
# this tool's three variants: "air"/"los"/"nlos" are all "drone emission
# only", just under different flight/visibility conditions, so they all
# map to DRONE. Any value not listed here (most notably "env", the
# `no_drone` ambient baseline) isn't a drone-emission variant at all.
_ROGUE_CORPUS_EXPERIMENT_TO_VARIANT: dict[str, Variant] = {
    "air": Variant.DRONE,
    "los": Variant.DRONE,
    "nlos": Variant.DRONE,
    "controller": Variant.CONTROLLER,
    "both": Variant.BOTH,
}


def scan_rogue_corpus(rec_dir: Path) -> ScanResult:
    """Scan a ROGUE drone-RF corpus campaign directory in place — e.g.
    point this at `recordings/drone-corpus/15June2022` directly, no
    copying. `no_drone` is always skipped (ambient/background, not a
    drone emission). When more than one recording in a drone's directory
    maps to the same variant, the first (sorted by filename) is kept and
    the rest are warned about and skipped — the same "pick one
    representative recording" approach `ingest_drone_corpus.py` already
    takes for its own purposes.
    """
    warnings: list[ScanWarning] = []
    drones: dict[str, DroneEntry] = {}

    for drone_dir in sorted(p for p in rec_dir.iterdir() if p.is_dir()):
        if drone_dir.name == "no_drone":
            continue

        variants: dict[Variant, Recording] = {}
        for meta_path in sorted(drone_dir.glob("*.sigmf-meta")):
            try:
                sig = fromfile(meta_path, skip_checksum=True)
            except Exception as exc:  # noqa: BLE001 - parse failure is a warning, not a crash
                warnings.append(
                    ScanWarning(str(meta_path), f"could not parse SigMF metadata: {exc}")
                )
                continue

            experiment = sig.get_global_field("experiment:scenario")
            variant = _ROGUE_CORPUS_EXPERIMENT_TO_VARIANT.get(experiment) if experiment else None
            if variant is None:
                warnings.append(
                    ScanWarning(
                        str(meta_path),
                        f"experiment:scenario {experiment!r} doesn't map to a "
                        "known variant, skipped",
                    )
                )
                continue
            if variant in variants:
                warnings.append(
                    ScanWarning(
                        str(meta_path),
                        f"another recording was already chosen for '{variant.value}'; "
                        "this one skipped",
                    )
                )
                continue
            variants[variant] = _build_recording(meta_path, warnings)

        entry = _finalize_drone(drone_dir.name, variants, warnings)
        if entry is not None:
            drones[drone_dir.name] = entry

    return ScanResult(catalog=Catalog(drones=drones), warnings=warnings)


def _finalize_drone(
    name: str, variants: dict[Variant, Recording], warnings: list[ScanWarning]
) -> DroneEntry | None:
    if not variants:
        warnings.append(ScanWarning(name, "no recognized variant recordings found, drone skipped"))
        return None
    entry = DroneEntry(variants=variants)
    for missing in entry.missing_variants:
        warnings.append(ScanWarning(name, f"missing '{missing.value}' variant"))
    return entry


def _build_recording(meta_path: Path, warnings: list[ScanWarning]) -> Recording:
    data_path = meta_path.with_suffix(".sigmf-data")
    kwargs: dict[str, Any] = {"meta": meta_path}
    if data_path.is_file():
        kwargs["data"] = data_path
    else:
        warnings.append(ScanWarning(str(meta_path), f"no companion {data_path.name} found"))

    try:
        sig = fromfile(meta_path, skip_checksum=True)
    except Exception as exc:  # noqa: BLE001 - any parse failure becomes a warning, not a crash
        warnings.append(ScanWarning(str(meta_path), f"could not parse SigMF metadata: {exc}"))
        return Recording(**kwargs)

    sample_rate_hz = sig.get_global_field("core:sample_rate")
    kwargs["datatype"] = sig.get_global_field("core:datatype")
    kwargs["sample_rate_hz"] = sample_rate_hz
    captures = sig.get_captures()
    if captures:
        kwargs["center_freq_hz"] = captures[0].get("core:frequency")
    if sample_rate_hz:
        kwargs["duration_s"] = sig.sample_count / sample_rate_hz
    return Recording(**kwargs)


def write_catalog(catalog: Catalog, out_path: Path) -> None:
    raw = {
        drone: {
            "variants": {
                variant.value: {
                    k: str(v) if isinstance(v, Path) else v
                    for k, v in rec.model_dump().items()
                    if v is not None
                }
                for variant, rec in entry.variants.items()
            },
            "notes": entry.notes,
        }
        for drone, entry in catalog.drones.items()
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(raw, sort_keys=False))
