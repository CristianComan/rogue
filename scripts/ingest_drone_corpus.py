#!/usr/bin/env python3
"""Ingest a representative sample of a Droids-style SigMF drone-RF corpus into
the local M4 catalogue (see docs/testing/manual-verification-guide.md).

Expects a source layout of ``<source_root>/<drone_id>/**/*.sigmf-meta`` (plus
matching ``.sigmf-data``), where ``<drone_id>`` is one subdirectory per drone
class (e.g. ``00``, ``01``, ...) or a baseline like ``no_drone`` — the layout
of the "Droids_data11" AIR-T/Deepwave capture campaigns. For each drone_id
directory this picks one file: by default, the first ``exp=air`` recording
at 2.45GHz if present, else the first ``exp=los``, then ``exp=env``,
``exp=controller``, ``exp=both``, ``exp=nlos``, then just the first
recording found — preferring ``fnum=0000000000`` when multiple takes exist.
Pass ``--scenario``/``--band`` to target a specific experiment instead (e.g.
``--scenario both --band 5800e6`` for "drone and controller both
transmitting, 5.8GHz band"); drone_id directories with no matching
recording are skipped rather than falling back. Platform name is read from
each recording's own ``classification:platform`` SigMF field.

Uploads the selected ``.sigmf-meta``/``.sigmf-data`` pair to the configured
S3-compatible bucket in 8MB chunks (never buffers a full recording in memory,
per CLAUDE.md's bounded-streaming rule) under
``drone-corpus/<campaign>/<drone_id>/...``, then registers it via
``POST /recordings`` against a running ROGUE API.

Rerunning is *not* idempotent: each run with no ``recording_id`` registers a
brand-new catalogue entry, so a second run duplicates entries rather than
erroring. Delete the old ``iq_recordings`` rows first if you want a clean
re-run.

Usage:
    python scripts/ingest_drone_corpus.py --source-root /path/to/campaign
    python scripts/ingest_drone_corpus.py --dry-run   # preview the selection only
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any

import boto3
import httpx
from boto3.s3.transfer import TransferConfig

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from rogue.settings import settings  # noqa: E402

_EXPERIMENT_PREFERENCE = ["air", "los", "env", "controller", "both", "nlos"]
_CHUNK_BYTES = 8 * 1024 * 1024


def _pick_meta_file(
    drone_dir: str, *, scenario: str | None = None, band: str | None = None
) -> str | None:
    """Pick one representative ``.sigmf-meta`` under a drone_id directory.

    With ``scenario``/``band`` given, only recordings matching both (via the
    ``exp=<scenario>_`` / ``fc=<band>_`` filename tokens) are considered, and
    ``None`` is returned if there's no match — no falling back to an
    unrelated experiment. Without them, falls back through
    ``_EXPERIMENT_PREFERENCE`` at whatever band is available.
    """
    all_metas = sorted(glob.glob(f"{drone_dir}/**/*.sigmf-meta", recursive=True))
    if not all_metas:
        return None

    if scenario is not None or band is not None:
        candidates = all_metas
        if scenario is not None:
            candidates = [m for m in candidates if f"exp={scenario}_" in os.path.basename(m)]
        if band is not None:
            candidates = [m for m in candidates if f"fc={band}_" in os.path.basename(m)]
        if not candidates:
            return None
        preferred_take = [c for c in candidates if "fnum=0000000000" in os.path.basename(c)]
        return sorted(preferred_take or candidates)[0]

    for exp in _EXPERIMENT_PREFERENCE:
        candidates = [m for m in all_metas if f"exp={exp}_" in os.path.basename(m)]
        if not candidates:
            continue
        preferred_take = [c for c in candidates if "fnum=0000000000" in os.path.basename(c)]
        return sorted(preferred_take or candidates)[0]

    return all_metas[0]


def select_recordings(
    source_root: str, *, scenario: str | None = None, band: str | None = None
) -> list[dict[str, Any]]:
    """Pick one representative recording per drone_id subdirectory of source_root."""
    if not os.path.isdir(source_root):
        raise FileNotFoundError(f"source root does not exist: {source_root}")

    selections: list[dict[str, Any]] = []
    for drone_id in sorted(os.listdir(source_root)):
        drone_dir = os.path.join(source_root, drone_id)
        if not os.path.isdir(drone_dir):
            continue

        meta_path = _pick_meta_file(drone_dir, scenario=scenario, band=band)
        if meta_path is None:
            print(f"!! no matching SigMF recording under {drone_dir}", file=sys.stderr)
            continue

        data_path = meta_path[: -len(".sigmf-meta")] + ".sigmf-data"
        if not os.path.exists(data_path):
            print(f"!! {meta_path} has no matching .sigmf-data, skipping", file=sys.stderr)
            continue

        with open(meta_path) as f:
            doc = json.load(f)
        global_fields = doc.get("global", {})
        platform = global_fields.get("classification:platform") or global_fields.get(
            "core:description", drone_id
        )
        scenario = global_fields.get("experiment:scenario", "unknown")

        selections.append(
            {
                "drone_id": drone_id,
                "platform": platform,
                "scenario": scenario,
                "meta_path": meta_path,
                "data_path": data_path,
                "data_size": os.path.getsize(data_path),
            }
        )
    return selections


def upload_and_register(
    selections: list[dict[str, Any]], *, campaign: str, api_base: str, access_classification: str
) -> list[dict[str, Any]]:
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )
    transfer_config = TransferConfig(
        multipart_threshold=_CHUNK_BYTES, multipart_chunksize=_CHUNK_BYTES
    )
    client = httpx.Client(base_url=api_base, timeout=60.0)

    results = []
    for sel in selections:
        drone_id, platform = sel["drone_id"], sel["platform"]
        meta_key = f"drone-corpus/{campaign}/{drone_id}/{os.path.basename(sel['meta_path'])}"
        data_key = f"drone-corpus/{campaign}/{drone_id}/{os.path.basename(sel['data_path'])}"

        print(f"[{drone_id}] {platform}: uploading to {settings.s3_bucket}...")
        s3.upload_file(sel["meta_path"], settings.s3_bucket, meta_key, Config=transfer_config)
        s3.upload_file(sel["data_path"], settings.s3_bucket, data_key, Config=transfer_config)

        provenance = (
            f"campaign={campaign}, drone_id={drone_id}, platform={platform}, "
            f"scenario={sel['scenario']}, real AIR-T/Deepwave capture "
            f"(source: {sel['meta_path']})"
        )
        resp = client.post(
            "/recordings",
            json={
                "metadata_object_key": meta_key,
                "data_object_key": data_key,
                "provenance": provenance,
                "access_classification": access_classification,
            },
        )
        if resp.status_code != 201:
            print(f"[{drone_id}] REJECTED ({resp.status_code}): {resp.text}")
            results.append({"drone_id": drone_id, "platform": platform, "status": "rejected"})
            continue

        rec = resp.json()["recording"]
        print(f"[{drone_id}] registered as {rec['id']} v{rec['version']}")
        results.append(
            {"drone_id": drone_id, "platform": platform, "status": "ok", "recording_id": rec["id"]}
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source-root", required=True, help="path to the campaign directory")
    parser.add_argument(
        "--campaign", default=None, help="campaign label for provenance/object keys "
        "(defaults to the source root's basename)"
    )
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument(
        "--access-classification",
        default="restricted",
        choices=["public", "restricted", "controlled"],
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="only consider recordings from this experiment (e.g. 'both', 'air', 'los'); "
        "default follows the built-in air/los/env/controller/both/nlos preference",
    )
    parser.add_argument(
        "--band",
        default=None,
        help="only consider recordings at this SigMF fc= band token (e.g. '5800e6', '2450e6'); "
        "default accepts whatever band the preferred experiment is available at",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the selection and exit without uploading"
    )
    args = parser.parse_args()
    campaign = args.campaign or os.path.basename(os.path.normpath(args.source_root))

    selections = select_recordings(args.source_root, scenario=args.scenario, band=args.band)
    if not selections:
        print("no recordings selected", file=sys.stderr)
        return 1

    total_mb = sum(s["data_size"] for s in selections) / 1e6
    print(f"{len(selections)} recordings selected ({total_mb:.1f} MB total):")
    for s in selections:
        print(f"  {s['drone_id']:>10}  {s['platform']:<30} scenario={s['scenario']}")

    if args.dry_run:
        return 0

    print()
    results = upload_and_register(
        selections,
        campaign=campaign,
        api_base=args.api_base,
        access_classification=args.access_classification,
    )
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n{ok}/{len(results)} ingested successfully")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
