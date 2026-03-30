# AGENTS.md

## Project
Build and maintain a Python FastAPI project named `prd_skill`.

## Goal
This service should support:
- session management
- interactive PRD generation
- reverse PRD generation
- PRD markdown output API

The system should be easy to extend later for:
- real LLM providers
- Redis session storage
- task generation for Codex
- project/file ingestion for reverse PRD

---

## Repository structure
- app.py: FastAPI entrypoint and route registration only
- prompts.py: prompt templates and prompt builders only
- schemas.py: Pydantic models, enums, request/response schemas
- service.py: core business logic
- session_store.py: session persistence abstraction and in-memory implementation
- llm.py: LLM abstraction and provider implementations

---

## Architecture rules
- Keep route handlers thin.
- Do not place business logic in route handlers.
- Do not place persistence logic in route handlers.
- Keep prompt text out of route handlers.
- Put all request/response schemas in `schemas.py`.
- Put orchestration logic in `service.py`.
- Keep `session_store.py` replaceable with Redis later.
- Keep `llm.py` replaceable with real model providers later.
- Prefer dependency injection over hard-coded globals.

---

## Coding rules
- Use Python 3.11+ style.
- Use type hints consistently.
- Use Pydantic for all API schemas.
- Prefer small functions with clear names.
- Avoid duplicated logic.
- Add docstrings to public classes and non-trivial functions.
- Raise clear exceptions and map them to HTTP errors in `app.py`.
- Do not silently swallow exceptions.
- Do not hard-code product-specific business content in the service layer.

---

## API rules

### Required endpoints
- `GET /health`
- `POST /session/start`
- `POST /session/continue`
- `POST /prd/generate`

### Request/response constraints
- Response models must be explicit and stable.
- Keep API payloads forward-compatible.

### /prd/generate request model (CRITICAL)
This endpoint must use a **mutually exclusive request shape**:

Allowed patterns:

1. Session-based:
   - session_id only

2. One-shot:
   - mode + input_text (+ optional project_context)

Invalid cases:
- Providing both session_id and input_text → return `INVALID_REQUEST_SHAPE`
- Providing neither → return `INVALID_REQUEST_SHAPE`

### Error response format (MANDATORY)
All errors must follow:

```json
{
  "error_code": "STRING_CODE",
  "message": "Human readable message",
  "details": {}
}