"""prd_skill 的 FastAPI 入口文件。

中文说明：
- 本文件只负责应用初始化、路由注册和异常映射
- 不承载业务编排、持久化逻辑或 LLM 调用细节
- 所有业务逻辑统一下沉到 service 层
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from llm import (
    BaseLLMProvider,
    LLMProviderJSONDecodeError,
    LLMProviderSchemaValidationError,
    LLMProviderUpstreamError,
    OpenAICompatibleLLMProvider,
    StubLLMProvider,
)
from settings import LLMProviderSettings, load_llm_provider_settings_from_env
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


def build_llm_provider_from_settings(settings: LLMProviderSettings) -> BaseLLMProvider:
    """中文说明：根据配置对象装配当前服务使用的 LLM provider。"""

    if settings.provider == "stub":
        return StubLLMProvider()
    if settings.provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(settings=settings)
    raise ValueError(f"Unsupported PRD_SKILL_LLM_PROVIDER: {settings.provider}")


def build_llm_provider_from_env() -> BaseLLMProvider:
    """中文说明：从环境变量加载配置并装配当前服务使用的 LLM provider。"""

    settings = load_llm_provider_settings_from_env()
    return build_llm_provider_from_settings(settings)

_session_store = InMemorySessionStore()
_llm_provider = build_llm_provider_from_env()
_service = PrdService(_session_store, _llm_provider)


def _error_response(status_code: int, error: ErrorResponse) -> JSONResponse:
    """中文说明：将标准错误模型包装为 JSONResponse。"""

    return JSONResponse(status_code=status_code, content=error.model_dump())


@app.exception_handler(SessionNotFoundError)
async def handle_session_not_found(
    _request: Request, exc: SessionNotFoundError
) -> JSONResponse:
    """中文说明：将会话不存在异常映射为 HTTP 404。"""

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
    """中文说明：将请求 shape 非法异常映射为 HTTP 400。"""

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
    """中文说明：将事实不足异常映射为 HTTP 400。"""

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
    """中文说明：将不支持模式异常映射为 HTTP 400。"""

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
    """中文说明：将请求校验异常映射为统一错误响应。"""

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
    """中文说明：兜底处理未显式映射的服务层异常。"""

    return _error_response(
        500,
        ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.exception_handler(LLMProviderUpstreamError)
async def handle_llm_upstream_error(
    _request: Request, exc: LLMProviderUpstreamError
) -> JSONResponse:
    """中文说明：将上游 LLM 调用失败映射为统一错误响应。"""

    return _error_response(
        502,
        ErrorResponse(
            error_code="LLM_UPSTREAM_ERROR",
            message=str(exc),
            details={},
        ),
    )


@app.exception_handler(LLMProviderJSONDecodeError)
async def handle_llm_json_decode_error(
    _request: Request, exc: LLMProviderJSONDecodeError
) -> JSONResponse:
    """中文说明：将 LLM 非法 JSON 响应映射为统一错误响应。"""

    return _error_response(
        502,
        ErrorResponse(
            error_code="LLM_JSON_DECODE_ERROR",
            message=str(exc),
            details={},
        ),
    )


@app.exception_handler(LLMProviderSchemaValidationError)
async def handle_llm_schema_validation_error(
    _request: Request, exc: LLMProviderSchemaValidationError
) -> JSONResponse:
    """中文说明：将 LLM JSON 结构错误映射为统一错误响应。"""

    return _error_response(
        502,
        ErrorResponse(
            error_code="LLM_SCHEMA_VALIDATION_ERROR",
            message=str(exc),
            details={},
        ),
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    responses={500: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def health() -> HealthResponse:
    """中文说明：返回服务健康状态。"""

    return HealthResponse(status="ok")


@app.post(
    "/session/start",
    response_model=SessionStartResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def start_session(request: SessionStartRequest) -> SessionStartResponse:
    """中文说明：启动新的 PRD 会话。"""

    return _service.start_session(request)


@app.post(
    "/session/continue",
    response_model=SessionContinueResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def continue_session(request: SessionContinueRequest) -> SessionContinueResponse:
    """中文说明：继续已有的 PRD 会话。"""

    return _service.continue_session(request)


@app.post(
    "/prd/generate",
    response_model=PrdGenerateResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def generate_prd(request: GeneratePrdRequest) -> PrdGenerateResponse:
    """中文说明：根据 session 或 one-shot 请求生成 PRD markdown。"""

    return _service.generate_prd(request)


@app.post(
    "/tasks/generate",
    response_model=TasksGenerateResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def generate_tasks(request: TasksGenerateRequest) -> TasksGenerateResponse:
    """中文说明：根据 PRD markdown 生成实现任务。"""

    return _service.generate_tasks(request)
