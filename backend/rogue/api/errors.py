"""Maps persistence-layer exceptions to HTTP responses.

Route handlers let ``rogue.persistence.repository`` exceptions propagate
rather than catching them individually; these handlers are the single
place that decides the HTTP status/body for each.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rogue.execution.orchestrator import InvalidRunTransitionError
from rogue.persistence import repository


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(repository.NotFoundError)
    async def _not_found(request: Request, exc: repository.NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(repository.ConflictError)
    async def _conflict(request: Request, exc: repository.ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(repository.ValidationRejectedError)
    async def _validation_rejected(
        request: Request, exc: repository.ValidationRejectedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "publish rejected: blocking validation findings",
                "findings": [f.model_dump(mode="json") for f in exc.findings],
            },
        )

    @app.exception_handler(repository.CompilationRejectedError)
    async def _compilation_rejected(
        request: Request, exc: repository.CompilationRejectedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "compilation rejected: blocking compiler findings",
                "findings": [f.model_dump(mode="json") for f in exc.findings],
            },
        )

    @app.exception_handler(InvalidRunTransitionError)
    async def _invalid_run_transition(
        request: Request, exc: InvalidRunTransitionError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})
