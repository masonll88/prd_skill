"""Core service layer for session management and PRD generation."""

from __future__ import annotations

import re
from typing import Optional
from uuid import uuid4

from llm import BaseLLMProvider
from prompts import (
    build_follow_up_prompt,
    build_interactive_prd_prompt,
    build_reverse_prd_prompt,
)
from schemas import (
    ExtractedFacts,
    GeneratePrdRequest,
    Message,
    MessageRole,
    PrdGenerateResponse,
    SessionContinueRequest,
    SessionContinueResponse,
    SessionMode,
    SessionStartRequest,
    SessionStartResponse,
    SessionState,
)
from session_store import SessionStore


REQUIRED_INTERACTIVE_FACTS = [
    "goal",
    "users",
    "scenarios",
    "core_functions",
    "conversion_path",
]


class ServiceError(Exception):
    """Base class for service-layer exceptions."""

    error_code = "SERVICE_ERROR"

    def __init__(
        self, message: str, details: Optional[dict[str, object]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SessionNotFoundError(ServiceError):
    """Raised when a session cannot be found."""

    error_code = "SESSION_NOT_FOUND"


class InvalidRequestShapeError(ServiceError):
    """Raised when /prd/generate receives an invalid shape."""

    error_code = "INVALID_REQUEST_SHAPE"


class InsufficientFactsError(ServiceError):
    """Raised when interactive generation lacks required facts."""

    error_code = "INSUFFICIENT_FACTS"


class UnsupportedModeError(ServiceError):
    """Raised when a mode is unsupported."""

    error_code = "UNSUPPORTED_MODE"


def _split_fact_items(value: str) -> list[str]:
    items = re.split(r"[,;\n|、]+", value)
    return [item.strip(" -") for item in items if item.strip(" -")]


def _find_keyword_value(text: str, keywords: list[str]) -> Optional[str]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        for keyword in keywords:
            if lowered.startswith(keyword):
                _, _, value = line.partition(":")
                if not value:
                    _, _, value = line.partition("：")
                cleaned = value.strip()
                if cleaned:
                    return cleaned
    return None


def _extract_list(text: str, keywords: list[str]) -> list[str]:
    value = _find_keyword_value(text, keywords)
    return _split_fact_items(value) if value else []


class PrdService:
    """Orchestrates session workflows and PRD generation."""

    def __init__(self, session_store: SessionStore, llm_provider: BaseLLMProvider) -> None:
        self._session_store = session_store
        self._llm_provider = llm_provider

    def start_session(self, request: SessionStartRequest) -> SessionStartResponse:
        """Create a new session and return its initial status."""

        session = SessionState(
            session_id=str(uuid4()),
            mode=request.mode,
            project_context=request.project_context,
        )
        if request.input_text:
            session.messages.append(Message(role=MessageRole.USER, content=request.input_text))
            session.turn_count += 1
            session.extracted_facts = self._extract_facts(
                mode=request.mode,
                existing=session.extracted_facts,
                input_text=request.input_text,
            )
        payload = self._build_session_payload(session)
        session.messages.append(Message(role=MessageRole.ASSISTANT, content=payload["next_prompt"]))
        self._session_store.create_session(session)
        return SessionStartResponse(**payload)

    def continue_session(
        self, request: SessionContinueRequest
    ) -> SessionContinueResponse:
        """Append user input to an existing session."""

        session = self._require_session(request.session_id)
        session.messages.append(Message(role=MessageRole.USER, content=request.input_text))
        session.turn_count += 1
        session.extracted_facts = self._extract_facts(
            mode=session.mode,
            existing=session.extracted_facts,
            input_text=request.input_text,
        )
        response = SessionContinueResponse(**self._build_session_payload(session))
        session.messages.append(
            Message(role=MessageRole.ASSISTANT, content=response.next_prompt)
        )
        self._session_store.save_session(session)
        return response

    def generate_prd(self, request: GeneratePrdRequest) -> PrdGenerateResponse:
        """Generate PRD markdown from a session or one-shot input."""

        self._validate_generate_request_shape(request)
        if request.session_id is not None:
            session = self._require_session(request.session_id)
            return self._generate_from_session(session)
        if request.mode is None or request.input_text is None:
            raise InvalidRequestShapeError(
                "mode and input_text are required for one-shot generation.",
                {"session_id": request.session_id, "mode": request.mode},
            )
        return self._generate_one_shot(
            mode=request.mode,
            input_text=request.input_text,
            project_context=request.project_context,
        )

    def _generate_from_session(self, session: SessionState) -> PrdGenerateResponse:
        if session.mode == SessionMode.INTERACTIVE:
            missing_information = self._missing_interactive_facts(session.extracted_facts)
            if missing_information:
                raise InsufficientFactsError(
                    "Interactive PRD generation requires all minimum facts.",
                    {
                        "missing_information": missing_information,
                        "session_id": session.session_id,
                    },
                )
            prompt = build_interactive_prd_prompt(
                facts=session.extracted_facts,
                project_context=session.project_context,
            )
            return PrdGenerateResponse(
                mode=session.mode,
                markdown=self._llm_provider.generate(prompt),
                missing_information=[],
                status="generated",
            )
        if session.mode == SessionMode.REVERSE:
            user_text = self._collect_user_text(session.messages)
            prompt = build_reverse_prd_prompt(user_text, session.project_context)
            missing_information = self._missing_reverse_information(user_text)
            return PrdGenerateResponse(
                mode=session.mode,
                markdown=self._llm_provider.generate(prompt),
                missing_information=missing_information,
                status="generated_with_gaps" if missing_information else "generated",
            )
        raise UnsupportedModeError(f"Unsupported session mode: {session.mode}")

    def _generate_one_shot(
        self,
        *,
        mode: SessionMode,
        input_text: str,
        project_context: Optional[str],
    ) -> PrdGenerateResponse:
        if mode == SessionMode.INTERACTIVE:
            facts = self._extract_facts(
                mode=mode,
                existing=ExtractedFacts(),
                input_text=input_text,
            )
            missing_information = self._missing_interactive_facts(facts)
            if missing_information:
                raise InsufficientFactsError(
                    "Interactive one-shot generation requires all minimum facts.",
                    {"missing_information": missing_information},
                )
            prompt = build_interactive_prd_prompt(facts, project_context)
            return PrdGenerateResponse(
                mode=mode,
                markdown=self._llm_provider.generate(prompt),
                missing_information=[],
                status="generated",
            )
        if mode == SessionMode.REVERSE:
            prompt = build_reverse_prd_prompt(input_text, project_context)
            missing_information = self._missing_reverse_information(input_text)
            return PrdGenerateResponse(
                mode=mode,
                markdown=self._llm_provider.generate(prompt),
                missing_information=missing_information,
                status="generated_with_gaps" if missing_information else "generated",
            )
        raise UnsupportedModeError(f"Unsupported session mode: {mode}")

    def _build_session_payload(self, session: SessionState) -> dict[str, object]:
        missing_information = (
            self._missing_interactive_facts(session.extracted_facts)
            if session.mode == SessionMode.INTERACTIVE
            else self._missing_reverse_information(self._collect_user_text(session.messages))
        )
        can_generate = (
            not missing_information
            if session.mode == SessionMode.INTERACTIVE
            else self._can_generate_reverse(session)
        )
        next_prompt = build_follow_up_prompt(session.mode, missing_information)
        return {
            "session_id": session.session_id,
            "mode": session.mode,
            "turn_count": session.turn_count,
            "extracted_facts": session.extracted_facts,
            "missing_information": missing_information,
            "can_generate": can_generate,
            "next_prompt": next_prompt,
            "status": self._resolve_session_status(session.mode, can_generate, missing_information),
        }

    def _extract_facts(
        self,
        *,
        mode: SessionMode,
        existing: ExtractedFacts,
        input_text: str,
    ) -> ExtractedFacts:
        if mode == SessionMode.REVERSE:
            return existing

        goal = _find_keyword_value(input_text, ["goal", "目标"])
        users = _extract_list(input_text, ["users", "用户"])
        scenarios = _extract_list(input_text, ["scenarios", "场景"])
        core_functions = _extract_list(input_text, ["core_functions", "核心功能", "functions"])
        conversion_path = _extract_list(
            input_text, ["conversion_path", "转化路径", "conversion"]
        )

        return ExtractedFacts(
            goal=goal or existing.goal,
            users=users or existing.users,
            scenarios=scenarios or existing.scenarios,
            core_functions=core_functions or existing.core_functions,
            conversion_path=conversion_path or existing.conversion_path,
        )

    def _missing_interactive_facts(self, facts: ExtractedFacts) -> list[str]:
        missing: list[str] = []
        for fact_name in REQUIRED_INTERACTIVE_FACTS:
            value = getattr(facts, fact_name)
            if not value:
                missing.append(fact_name)
        return missing

    def _can_generate_reverse(self, session: SessionState) -> bool:
        return any(message.role == MessageRole.USER for message in session.messages)

    def _missing_reverse_information(self, input_text: str) -> list[str]:
        text = input_text.strip()
        if not text:
            return REQUIRED_INTERACTIVE_FACTS.copy()

        facts = self._extract_facts(
            mode=SessionMode.INTERACTIVE,
            existing=ExtractedFacts(),
            input_text=text,
        )
        missing = self._missing_interactive_facts(facts)
        if not missing:
            return []

        fallback_keywords = {
            "goal": ["目标", "goal", "提升", "降低", "增长"],
            "users": ["用户", "角色", "运营", "商家", "客户"],
            "scenarios": ["场景", "使用", "流程", "场景化"],
            "core_functions": ["功能", "能力", "支持", "配置", "创建"],
            "conversion_path": ["转化", "路径", "漏斗", "激活", "留存"],
        }
        lowered = text.lower()
        inferred_missing: list[str] = []
        for field in missing:
            keywords = fallback_keywords[field]
            if not any(keyword.lower() in lowered for keyword in keywords):
                inferred_missing.append(field)
        return inferred_missing

    def _resolve_session_status(
        self, mode: SessionMode, can_generate: bool, missing_information: list[str]
    ) -> str:
        if mode == SessionMode.INTERACTIVE:
            return "ready" if can_generate else "needs_input"
        if missing_information:
            return "draft_with_gaps"
        return "ready"

    def _validate_generate_request_shape(self, request: GeneratePrdRequest) -> None:
        has_session = request.session_id is not None
        has_one_shot_input = request.input_text is not None
        if has_session and has_one_shot_input:
            raise InvalidRequestShapeError(
                "Provide either session_id or input_text, but not both.",
                {"session_id": request.session_id, "input_text": True},
            )
        if not has_session and not has_one_shot_input:
            raise InvalidRequestShapeError(
                "Provide either session_id or mode + input_text.",
                {},
            )
        if has_session and (request.mode is not None or request.project_context is not None):
            raise InvalidRequestShapeError(
                "Session-based generation only accepts session_id.",
                {"mode": request.mode, "project_context": request.project_context},
            )
        if has_one_shot_input and request.mode is None:
            raise InvalidRequestShapeError(
                "One-shot generation requires mode + input_text.",
                {"mode": request.mode},
            )

    def _collect_user_text(self, messages: list[Message]) -> str:
        user_messages = [message.content for message in messages if message.role == MessageRole.USER]
        return "\n".join(user_messages)

    def _require_session(self, session_id: str) -> SessionState:
        session = self._session_store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(
                f"Session '{session_id}' was not found.",
                {"session_id": session_id},
            )
        return session
