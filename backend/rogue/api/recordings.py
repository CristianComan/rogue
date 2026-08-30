"""SigMF catalogue ingest/list API (M4).

Ingest orchestration (fetch objects from S3, parse SigMF metadata, validate,
persist) lives in ``rogue.catalogue.ingest`` / ``rogue.persistence.catalogue``;
this module only translates HTTP <-> domain calls, matching
``rogue.api.scenarios``'s split.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.api.idempotency import replay_or_execute
from rogue.api.schemas import RecordingIngestRequest, SpectrogramResponse
from rogue.catalogue.sigmf import bytes_per_sample
from rogue.catalogue.spectrogram import compute_spectrogram, decode_iq_samples
from rogue.db.session import get_session
from rogue.domain.recording import AccessClassification, IQRecording
from rogue.persistence import catalogue
from rogue.persistence.repository import NotFoundError
from rogue.storage import object_store

router = APIRouter(prefix="/recordings", tags=["recordings"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]

_MAX_SPECTROGRAM_WINDOW_S = 10.0


@router.post("", status_code=201)
async def ingest_recording(
    request: RecordingIngestRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    async def execute() -> tuple[int, dict[str, Any]]:
        recording, findings = await catalogue.ingest_recording(
            session,
            recording_id=request.recording_id,
            metadata_object_key=request.metadata_object_key,
            data_object_key=request.data_object_key,
            provenance=request.provenance,
            access_classification=request.access_classification,
            allowed_use_constraints=request.allowed_use_constraints,
            allowed_frequency_min_hz=request.allowed_frequency_min_hz,
            allowed_frequency_max_hz=request.allowed_frequency_max_hz,
        )
        body = {
            "recording": recording.model_dump(mode="json"),
            "findings": [f.model_dump(mode="json") for f in findings],
        }
        return 201, body

    status_code, body = await replay_or_execute(
        session, idempotency_key, "POST /recordings", request.model_dump_json(), execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("", response_model=list[IQRecording])
async def list_recordings(
    session: SessionDep,
    access_classification: AccessClassification | None = None,
    provenance_contains: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[IQRecording]:
    """List the latest version of each catalogue entry."""
    return await catalogue.list_latest_recordings(
        session,
        access_classification=access_classification,
        provenance_contains=provenance_contains,
        limit=limit,
        offset=offset,
    )


@router.get("/{recording_id}", response_model=IQRecording)
async def get_recording(recording_id: UUID, session: SessionDep) -> IQRecording:
    """Fetch the latest version of a catalogue entry."""
    recording = await catalogue.get_recording(session, recording_id)
    if recording is None:
        raise NotFoundError(f"recording {recording_id} does not exist")
    return recording


@router.get("/{recording_id}/spectrogram", response_model=SpectrogramResponse)
async def get_recording_spectrogram(
    recording_id: UUID,
    session: SessionDep,
    window_start_s: Annotated[float, Query(ge=0)] = 0.0,
    window_duration_s: Annotated[float, Query(gt=0, le=_MAX_SPECTROGRAM_WINDOW_S)] = 1.0,
    fft_size: Annotated[int, Query(ge=64, le=8192)] = 1024,
) -> SpectrogramResponse:
    """A bounded time/frequency dB preview of the recording's I/Q content.

    Computed from a range-read of just the requested window's bytes — never
    the full recording (CLAUDE.md rule 8) — so ``window_duration_s`` is
    capped at ``_MAX_SPECTROGRAM_WINDOW_S`` regardless of the recording's
    actual length.
    """
    recording = await catalogue.get_recording(session, recording_id)
    if recording is None:
        raise NotFoundError(f"recording {recording_id} does not exist")

    sample_size = bytes_per_sample(recording.sample_format)
    if sample_size is None:
        raise HTTPException(
            422,
            detail=f"unsupported sample_format {recording.sample_format!r} for spectrogram",
        )

    total_bytes = recording.sample_count * sample_size
    offset_bytes = int(window_start_s * recording.sample_rate_hz) * sample_size
    if offset_bytes >= total_bytes:
        raise HTTPException(
            422,
            detail=(
                f"window_start_s={window_start_s} is at or beyond the recording's "
                f"duration_s={recording.duration_s}"
            ),
        )
    requested_bytes = int(window_duration_s * recording.sample_rate_hz) * sample_size
    length_bytes = min(requested_bytes, total_bytes - offset_bytes)

    try:
        raw = await asyncio.to_thread(
            object_store.get_object_range, recording.data_object_key, offset_bytes, length_bytes
        )
    except object_store.ObjectNotFoundError as exc:
        raise NotFoundError(f"recording data object is missing from storage: {exc}") from exc

    samples = decode_iq_samples(raw, recording.sample_format)
    result = compute_spectrogram(samples, recording.sample_rate_hz, fft_size=fft_size)
    return SpectrogramResponse(
        time_offsets_s=result.time_offsets_s,
        freq_offsets_hz=result.freq_offsets_hz,
        magnitude_db=result.magnitude_db,
    )


@router.get("/{recording_id}/versions", response_model=list[IQRecording])
async def list_recording_versions(recording_id: UUID, session: SessionDep) -> list[IQRecording]:
    versions = await catalogue.list_recording_versions(session, recording_id)
    if not versions:
        raise NotFoundError(f"recording {recording_id} does not exist")
    return versions


@router.get("/{recording_id}/versions/{version}", response_model=IQRecording)
async def get_recording_version(
    recording_id: UUID, version: int, session: SessionDep
) -> IQRecording:
    recording = await catalogue.get_recording(session, recording_id, version)
    if recording is None:
        raise NotFoundError(f"recording {recording_id} has no version {version}")
    return recording
