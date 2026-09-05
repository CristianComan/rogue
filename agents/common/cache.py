"""Local SigMF cache (M8, ADR-008, sdr-architecture.md §6): "I/Q is
prefetched before a run, checksum-verified and replayed from local
storage."

Reuses ``rogue.storage.object_store``'s bounded-streaming reads as-is —
``stream_object_to_file`` never loads the (potentially large)
``.sigmf-data`` object fully into memory, and is synchronous like the rest
of that module (its own docstring: "callers on the async request path must
run them via ``asyncio.to_thread``"). Skips re-download when a
validly-hashed copy already sits in the cache directory, since the whole
point of a *local* cache is not re-fetching bytes a previous run already
verified.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import UUID

from rogue.protocol.messages import RecordingCacheEntry
from rogue.storage import object_store

logger = logging.getLogger("rogue.agent.cache")


class CacheVerificationError(Exception):
    """Raised when a downloaded object's checksum doesn't match the pinned hash."""


def data_path_for(cache_dir: Path, recording_id: UUID, version: int) -> Path:
    """The cached ``.sigmf-data`` path for one recording version.

    Public so a real vendor adapter (``agents/common/x440_adapter.py``, M9)
    can find bytes this module already downloaded during ``PREFLIGHT``,
    without re-deriving the naming convention.
    """
    return cache_dir / f"{recording_id}.v{version}.sigmf-data"


def _paths(cache_dir: Path, entry: RecordingCacheEntry) -> tuple[Path, Path]:
    stem = f"{entry.recording_id}.v{entry.version}"
    data_path = data_path_for(cache_dir, entry.recording_id, entry.version)
    return cache_dir / f"{stem}.sigmf-meta", data_path


def _sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_valid_cache_hit(meta_path: Path, data_path: Path, entry: RecordingCacheEntry) -> bool:
    if not (meta_path.exists() and data_path.exists()):
        return False
    return _sha256_of_file(data_path) == entry.sha256_data


def _download(meta_path: Path, data_path: Path, entry: RecordingCacheEntry) -> None:
    meta_bytes = object_store.get_object_bytes(entry.metadata_object_key)
    digest = object_store.stream_object_to_file(entry.data_object_key, data_path)
    if digest.sha256 != entry.sha256_data:
        data_path.unlink(missing_ok=True)
        raise CacheVerificationError(
            f"recording {entry.recording_id} v{entry.version}: downloaded data does not match "
            f"the pinned sha256 ({digest.sha256} != {entry.sha256_data})"
        )
    meta_path.write_bytes(meta_bytes)


async def ensure_cached(cache_dir: Path, entry: RecordingCacheEntry) -> None:
    """Download+verify one recording into ``cache_dir`` unless a valid copy
    already exists there. Raises ``CacheVerificationError`` if the freshly
    downloaded bytes don't match the pinned hash — a preflight failure, not
    silently accepted.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_path, data_path = _paths(cache_dir, entry)

    if await asyncio.to_thread(_is_valid_cache_hit, meta_path, data_path, entry):
        logger.info("cache hit for recording %s v%s", entry.recording_id, entry.version)
        return

    logger.info("cache miss for recording %s v%s; downloading", entry.recording_id, entry.version)
    await asyncio.to_thread(_download, meta_path, data_path, entry)
