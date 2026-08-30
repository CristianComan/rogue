"""Bounded-streaming reads of SigMF assets from S3-compatible object storage.

Per docs/architecture/system-design.md, recording bytes live in MinIO, not in
the control-plane database or Git (CLAUDE.md rule 8). This module only reads
back a small ``.sigmf-meta`` JSON object in full and streams the (potentially
large) ``.sigmf-data`` object in bounded chunks to compute its checksum and
length — it never loads a full recording into memory (CLAUDE.md coding rule
on bounded streaming buffers).

Calls here are synchronous (boto3 has no native asyncio client); callers on
the async request path must run them via ``asyncio.to_thread``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError

from rogue.settings import settings

_STREAM_CHUNK_BYTES = 1024 * 1024


class ObjectNotFoundError(Exception):
    """Raised when a referenced object key does not exist in the bucket."""

    def __init__(self, key: str) -> None:
        super().__init__(f"object {key!r} does not exist")
        self.key = key


@dataclass(frozen=True)
class ObjectDigest:
    """Checksum(s) and byte length of a streamed object."""

    sha256: str
    sha512: str
    size_bytes: int


def _client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def _get_object(key: str, *, byte_range: tuple[int, int] | None = None) -> Any:
    kwargs: dict[str, Any] = {"Bucket": settings.s3_bucket, "Key": key}
    if byte_range is not None:
        offset, length = byte_range
        # HTTP Range is an inclusive end byte, hence the -1.
        kwargs["Range"] = f"bytes={offset}-{offset + length - 1}"
    try:
        return _client().get_object(**kwargs)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in ("NoSuchKey", "404"):
            raise ObjectNotFoundError(key) from exc
        raise


def get_object_bytes(key: str) -> bytes:
    """Fetch a small object (e.g. ``.sigmf-meta``) fully into memory."""
    response = _get_object(key)
    body: bytes = response["Body"].read()
    return body


def get_object_range(key: str, offset: int, length: int) -> bytes:
    """Fetch exactly ``length`` bytes of ``key`` starting at ``offset``.

    Uses an HTTP Range GET (MinIO/S3 both support it), so this stays bounded
    regardless of the underlying object's size — the spectrogram endpoint
    uses this to read only the requested time window's worth of I/Q samples,
    never the full recording.
    """
    response = _get_object(key, byte_range=(offset, length))
    body: bytes = response["Body"].read()
    return body


def digest_object(key: str) -> ObjectDigest:
    """Stream an object in bounded chunks, returning its checksums and length.

    Used for the ``.sigmf-data`` file, which may be arbitrarily large.
    """
    response = _get_object(key)
    sha256_hasher = hashlib.sha256()
    sha512_hasher = hashlib.sha512()
    size = 0
    for chunk in response["Body"].iter_chunks(chunk_size=_STREAM_CHUNK_BYTES):
        sha256_hasher.update(chunk)
        sha512_hasher.update(chunk)
        size += len(chunk)
    return ObjectDigest(
        sha256=sha256_hasher.hexdigest(), sha512=sha512_hasher.hexdigest(), size_bytes=size
    )
