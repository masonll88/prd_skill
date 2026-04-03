"""FastAPI entrypoint for the PRD skill service."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from llm import StubLLMProvider
from schemas import (
    ErrorResponse,
    GeneratePrdRequest,
    HealthResponse,
    TasksGenerateRequest,
    TasksGenerateResponse,
    SessionContinueRequest,
    SessionContinueResponse,
    SessionStartRequest,
    SessionStartResponse,
    PrdGenerateResponse,
)
from service import (
    InsufficientFactsError,
    InvalidRequestShapeError,
    PrdService,
    ServiceError,
    SessionNotFoundError,
    UnsupportedModeError,
)
from session_store import InMemorySessionStore

app = FastAPI(title="prd_skill")

_session_store = InMemorySessionStore()
_llm_provider = StubLLMProvider()
_service = PrdService(_session_store, _llm_provider)


def _error_response(status_code: int, error: ErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error.model_dump())


@app.exception_handler(SessionNotFoundError)
async def handle_session_not_found(
    _request: Request, exc: SessionNotFoundError
) -> JSONResponse:
    """Map missing session errors to HTTP 404."""

    return _error_response(
        404,
        ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.exception_handler(InvalidRequestShapeError)
async def handle_invalid_request_shape(
    _request: Request, exc: InvalidRequestShapeError
) -> JSONResponse:
    """Map invalid request shape errors to HTTP 400."""

    return _error_response(
        400,
        ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.exception_handler(InsufficientFactsError)
async def handle_insufficient_facts(
    _request: Request, exc: InsufficientFactsError
) -> JSONResponse:
    """Map insufficient fact errors to HTTP 400."""

    return _error_response(
        400,
        ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.exception_handler(UnsupportedModeError)
async def handle_unsupported_mode(
    _request: Request, exc: UnsupportedModeError
) -> JSONResponse:
    """Map unsupported mode errors to HTTP 400."""

    return _error_response(
        400,
        ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return the standard error model for request validation errors."""

    return _error_response(
        422,
        ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Request validation failed.",
            details={"errors": exc.errors()},
        ),
    )


@app.exception_handler(ServiceError)
async def handle_service_error(_request: Request, exc: ServiceError) -> JSONResponse:
    """Fallback mapping for unhandled service errors."""

    return _error_response(
        500,
        ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    responses={500: {"model": ErrorResponse}},
)
async def health() -> HealthResponse:
    """Return service health."""

    return HealthResponse(status="ok")


@app.post(
    "/session/start",
    response_model=SessionStartResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def start_session(request: SessionStartRequest) -> SessionStartResponse:
    """Start a PRD session."""

    return _service.start_session(request)


@app.post(
    "/session/continue",
    response_model=SessionContinueResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def continue_session(request: SessionContinueRequest) -> SessionContinueResponse:
    """Continue a PRD session."""

    return _service.continue_session(request)


@app.post(
    "/prd/generate",
    response_model=PrdGenerateResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def generate_prd(request: GeneratePrdRequest) -> PrdGenerateResponse:
    """Generate PRD markdown from a session or one-shot payload."""

    return _service.generate_prd(request)


@app.post(
    "/tasks/generate",
    response_model=TasksGenerateResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def generate_tasks(request: TasksGenerateRequest) -> TasksGenerateResponse:
    """Generate implementation tasks from PRD markdown."""

    return _service.generate_tasks(request)
