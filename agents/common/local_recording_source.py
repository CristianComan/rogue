"""Local-SigMF-root recording source for the Agent (ADR-019, M19b).

An alternative to `agents/common/cache.py`'s MinIO fetch, for PREFLIGHT when
the control plane (and MinIO with it) is unreachable: resolves a recording
already present under a locally-configured root — e.g. a technician's
laptop with previously-published SigMF files copied over ahead of time —
into the same cache-directory layout `cache.ensure_cached` produces, so
`agents.common.agent._load_cached_recording` reads it identically regardless
of which source populated the cache; it does not fork per ingress path.

No bytes are copied — the verified files are symlinked into `cache_dir`,
since a `.sigmf-data` file can be many gigabytes (CLAUDE.md rule 8: I/Q data
is never routed anywhere that would require duplicating it on disk for a
purely local operation).

Rejects the same failure class `cache.py` already enforces for the MinIO
path (a data hash that doesn't match the pinned `sha256_data`, raised as the
same `cache.CacheVerificationError` the NATS path's exception handling
already knows about — `agent.py`'s dispatch doesn't need a new except
clause), plus a missing metadata/data pair and path traversal/symlink escape
outside the configured root — a check the MinIO path gets for free from
object-store keys not being filesystem paths at all.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from agents.common import cache
from rogue.protocol.messages import RecordingCacheEntry

logger = logging.getLogger("rogue.agent.local_recording_source")


def _sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_within_root(local_root: Path, file_name: str) -> Path:
    """Resolves `file_name` under `local_root`, following symlinks, and
    rejects a result that escapes `local_root` (`../` traversal in the name,
    or a symlink pointing outside it).
    """
    root = local_root.resolve()
    candidate = (root / file_name).resolve()
    if candidate != root and root not in candidate.parents:
        raise cache.CacheVerificationError(
            f"{file_name!r} resolves outside the configured local recording root {local_root}"
        )
    return candidate


def _source_paths(local_root: Path, recording_id: UUID, version: int) -> tuple[Path, Path]:
    """The same `{recording_id}.v{version}.sigmf-{meta,data}` naming
    `cache.py`'s own `meta_path_for`/`data_path_for` use, so a local root is
    populated by copying files straight out of a previous `cache_dir` (or
    the object store) under matching names — no separate local naming
    scheme to keep in sync.
    """
    return (
        _resolve_within_root(local_root, f"{recording_id}.v{version}.sigmf-meta"),
        _resolve_within_root(local_root, f"{recording_id}.v{version}.sigmf-data"),
    )


async def ensure_cached(local_root: Path, cache_dir: Path, entry: RecordingCacheEntry) -> None:
    """The local-root counterpart to `cache.ensure_cached` — same effect:
    after this returns, `cache.meta_path_for`/`data_path_for(cache_dir,
    ...)` resolve to a hash-verified `.sigmf-meta`/`.sigmf-data` pair, ready
    for `agent.py`'s `_load_cached_recording` to read exactly as it does for
    a MinIO-fetched recording.
    """
    meta_src, data_src = _source_paths(local_root, entry.recording_id, entry.version)
    if not meta_src.is_file() or not data_src.is_file():
        raise cache.CacheVerificationError(
            f"recording {entry.recording_id} v{entry.version} not found under {local_root} "
            f"(expected {meta_src.name} and {data_src.name})"
        )

    digest = _sha256_of_file(data_src)
    if digest != entry.sha256_data:
        raise cache.CacheVerificationError(
            f"recording {entry.recording_id} v{entry.version}: local data does not match the "
            f"pinned sha256 ({digest} != {entry.sha256_data})"
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_dst = cache.meta_path_for(cache_dir, entry.recording_id, entry.version)
    data_dst = cache.data_path_for(cache_dir, entry.recording_id, entry.version)
    for dst, src in ((meta_dst, meta_src), (data_dst, data_src)):
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        dst.symlink_to(src)
    logger.info(
        "resolved recording %s v%s from local root %s",
        entry.recording_id,
        entry.version,
        local_root,
    )
