"""Pydantic schemas and enums for the PRD skill service."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SessionMode(str, Enum):
    """Supported session modes."""

    INTERACTIVE = "interactive"
    REVERSE = "reverse"


class MessageRole(str, Enum):
    """Supported message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A single chat message stored in a session."""

    role: MessageRole
    content: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractedFacts(BaseModel):
    """Semi-structured facts extracted from user input."""

    goal: Optional[str] = None
    users: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    core_functions: list[str] = Field(default_factory=list)
    conversion_path: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    """Persisted state for an active PRD session."""

    session_id: str
    mode: SessionMode
    messages: list[Message] = Field(default_factory=list)
    extracted_facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    turn_count: int = 0
    project_context: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response returned by all endpoints."""

    error_code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


class SessionStartRequest(BaseModel):
    """Request body for starting a session."""

    mode: SessionMode
    input_text: Optional[str] = None
    project_context: Optional[str] = None


class SessionContinueRequest(BaseModel):
    """Request body for continuing an existing session."""

    session_id: str = Field(min_length=1)
    input_text: str = Field(min_length=1)


class GeneratePrdRequest(BaseModel):
    """Normalized PRD generation request.

    This schema only normalizes optional string fields.
    The mutually exclusive request shape is enforced in the service layer.
    """

    session_id: Optional[str] = None
    mode: Optional[SessionMode] = None
    input_text: Optional[str] = None
    project_context: Optional[str] = None

    @model_validator(mode="after")
    def normalize_strings(self) -> "GeneratePrdRequest":
        """Normalize blank strings to None for shape validation downstream."""

        if self.session_id is not None and not self.session_id.strip():
            self.session_id = None
        if self.input_text is not None and not self.input_text.strip():
            self.input_text = None
        if self.project_context is not None and not self.project_context.strip():
            self.project_context = None
        return self


class SessionStatusResponse(BaseModel):
    """Shared response fields for session-based interactions."""

    session_id: str
    mode: SessionMode
    turn_count: int
    extracted_facts: ExtractedFacts
    missing_information: list[str]
    can_generate: bool
    next_prompt: str
    status: str


class SessionStartResponse(SessionStatusResponse):
    """Response returned when a session starts."""


class SessionContinueResponse(SessionStatusResponse):
    """Response returned when a session continues."""


class PrdGenerateResponse(BaseModel):
    """Generated PRD markdown response."""

    mode: SessionMode
    markdown: str
    missing_information: list[str]
    status: str


class TaskItem(BaseModel):
    """A single implementation task derived from a PRD."""

    title: str
    category: str
    priority: str
    milestone: str
    objective: str
    deliverable: str


class TasksGenerateRequest(BaseModel):
    """Request body for task generation from PRD markdown."""

    prd_markdown: str = Field(min_length=1)
    project_name: Optional[str] = None
    mode: Optional[SessionMode] = None
    project_context: Optional[str] = None


class TasksGenerateResponse(BaseModel):
    """Response containing decomposed tasks and execution prompts."""

    tasks: list[TaskItem]
    task_markdown: str
    implement_markdown: str
    codex_prompt: str
