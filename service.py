"""Core service layer for session management and PRD generation."""

from __future__ import annotations

import re
from typing import Optional
from uuid import uuid4

from llm import BaseLLMProvider
from prompts import (
    build_codex_execution_prompt,
    build_implement_markdown,
    build_reverse_prd_prompt,
    build_task_generation_prompt,
    render_next_prompt,
)
from schemas import (
    ExtractedFacts,
    FactExtractionResult,
    GeneratePrdRequest,
    InteractiveSessionStatus,
    Message,
    MessageRole,
    OpenQuestion,
    PrdGenerateResponse,
    PrdQuality,
    SessionContinueRequest,
    SessionContinueResponse,
    SessionMode,
    SessionStartRequest,
    SessionStartResponse,
    SessionState,
    TaskItem,
    TasksGenerateRequest,
    TasksGenerateResponse,
)
from session_store import SessionStore


DRAFT_REQUIRED_FIELDS = [
    "goal",
    "users",
    "scenarios",
    "core_functions",
    "conversion_path",
]

FINAL_REQUIRED_FIELDS = [
    "constraints",
    "success_metrics",
    "platform",
    "delivery_scope",
]

class ServiceError(Exception):
    """服务层异常基类。"""

    error_code = "SERVICE_ERROR"

    def __init__(
        self, message: str, details: Optional[dict[str, object]] = None
    ) -> None:
        """中文说明：初始化服务层异常。

        输入：错误消息、可选错误详情。
        输出：异常实例。
        关键逻辑：统一封装标准错误码和 details 供 app.py 映射。
        """

        super().__init__(message)
        self.message = message
        self.details = details or {}


class SessionNotFoundError(ServiceError):
    """会话不存在时抛出的异常。"""

    error_code = "SESSION_NOT_FOUND"


class InvalidRequestShapeError(ServiceError):
    """请求 shape 不符合约束时抛出的异常。"""

    error_code = "INVALID_REQUEST_SHAPE"


class InsufficientFactsError(ServiceError):
    """interactive 生成事实不足时抛出的异常。"""

    error_code = "INSUFFICIENT_FACTS"


class UnsupportedModeError(ServiceError):
    """模式不受支持时抛出的异常。"""

    error_code = "UNSUPPORTED_MODE"


def _split_fact_items(value: str) -> list[str]:
    """中文说明：拆分字符串中的多值事实项。

    输入：使用逗号、分号、换行或竖线连接的文本。
    输出：去空白后的列表。
    关键逻辑：用于 reverse 模式的轻量缺失信息推断。
    """

    items = re.split(r"[,;\n|、]+", value)
    return [item.strip(" -") for item in items if item.strip(" -")]


def _find_keyword_value(text: str, keywords: list[str]) -> Optional[str]:
    """中文说明：从文本中按关键词提取单值字段。

    输入：原始文本、可匹配关键词列表。
    输出：提取值，未命中时返回 `None`。
    关键逻辑：兼容中英文关键词和中英文冒号。
    """

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
    """中文说明：从文本中提取列表字段。

    输入：原始文本、可匹配关键词列表。
    输出：列表值。
    关键逻辑：仅用于 reverse 的保守缺失判断，不承担 interactive v2 合并逻辑。
    """

    value = _find_keyword_value(text, keywords)
    return _split_fact_items(value) if value else []


class PrdService:
    """Orchestrates session workflows and PRD generation."""

    def __init__(self, session_store: SessionStore, llm_provider: BaseLLMProvider) -> None:
        """中文说明：初始化服务层编排对象。

        输入：session store、LLM provider。
        输出：服务实例。
        关键逻辑：通过依赖注入保持 session 与 LLM 实现可替换。
        """

        self._session_store = session_store
        self._llm_provider = llm_provider

    def start_session(self, request: SessionStartRequest) -> SessionStartResponse:
        """中文说明：创建新会话并返回初始状态。

        输入：会话启动请求。
        输出：包含 facts、open questions 与下一问的响应。
        关键逻辑：interactive 会在首轮就做事实抽取与高价值追问。
        """

        session = SessionState(
            session_id=str(uuid4()),
            mode=request.mode,
            project_context=request.project_context,
        )
        if request.input_text:
            session.messages.append(Message(role=MessageRole.USER, content=request.input_text))
            session.turn_count += 1
        extraction = self._build_initial_extraction(session, request.input_text)
        payload = self._build_session_payload(session=session, extraction=extraction)
        session.extracted_facts = payload["extracted_facts"]
        session.messages.append(Message(role=MessageRole.ASSISTANT, content=payload["next_prompt"]))
        self._session_store.create_session(session)
        return SessionStartResponse(**payload)

    def continue_session(
        self, request: SessionContinueRequest
    ) -> SessionContinueResponse:
        """中文说明：向已有会话追加一轮输入并返回更新后的状态。

        输入：继续会话请求。
        输出：新的 facts、open questions、状态和下一问。
        关键逻辑：interactive 使用 LLM 抽取结果做多轮收敛，reverse 保持原有轻量行为。
        """

        session = self._require_session(request.session_id)
        session.messages.append(Message(role=MessageRole.USER, content=request.input_text))
        session.turn_count += 1
        extraction = self._extract_session_facts(session, request.input_text)
        payload = self._build_session_payload(session=session, extraction=extraction)
        session.extracted_facts = payload["extracted_facts"]
        session.messages.append(Message(role=MessageRole.ASSISTANT, content=payload["next_prompt"]))
        self._session_store.save_session(session)
        return SessionContinueResponse(**payload)

    def generate_prd(self, request: GeneratePrdRequest) -> PrdGenerateResponse:
        """中文说明：从 session 或 one-shot 请求生成 PRD。

        输入：PRD 生成请求。
        输出：生成结果和状态。
        关键逻辑：interactive 支持 draft/final，reverse 接受但忽略 quality。
        """

        self._validate_generate_request_shape(request)
        if request.session_id is not None:
            session = self._require_session(request.session_id)
            return self._generate_from_session(session, request.quality)
        if request.mode is None or request.input_text is None:
            raise InvalidRequestShapeError(
                "mode and input_text are required for one-shot generation.",
                {"session_id": request.session_id, "mode": request.mode},
            )
        return self._generate_one_shot(
            mode=request.mode,
            input_text=request.input_text,
            project_context=request.project_context,
            quality=request.quality,
        )

    def generate_tasks(self, request: TasksGenerateRequest) -> TasksGenerateResponse:
        """中文说明：根据 PRD markdown 生成实现任务。

        输入：任务生成请求。
        输出：任务列表、任务 markdown 与执行提示。
        关键逻辑：保持现有任务拆解能力，不受 interactive v2 改造影响。
        """

        summary = self._summarize_prd(request.prd_markdown)
        task_generation_prompt = build_task_generation_prompt(summary)
        sections = self._extract_prd_sections(request.prd_markdown)
        tasks = self._build_tasks_from_sections(sections)
        project_name = request.project_name or "prd_skill"
        milestones = self._collect_milestones(tasks)
        task_markdown = self._build_tasks_markdown(tasks, task_generation_prompt, project_name)
        implement_markdown = build_implement_markdown(
            project_name=project_name,
            milestones=milestones,
            project_context=request.project_context,
        )
        codex_prompt = build_codex_execution_prompt(task_markdown + "\n\n" + implement_markdown)
        return TasksGenerateResponse(
            tasks=tasks,
            task_markdown=task_markdown,
            implement_markdown=implement_markdown,
            codex_prompt=codex_prompt,
        )

    def _generate_from_session(
        self, session: SessionState, requested_quality: Optional[PrdQuality]
    ) -> PrdGenerateResponse:
        """中文说明：基于已有 session 生成 PRD。

        输入：会话状态、请求质量档位。
        输出：PRD 生成结果。
        关键逻辑：interactive 走 v2 判定，reverse 保持原有单档逻辑并忽略 quality。
        """

        if session.mode == SessionMode.INTERACTIVE:
            quality = requested_quality or PrdQuality.FINAL
            interactive_snapshot = self._build_interactive_snapshot(
                facts=session.extracted_facts,
                project_context=session.project_context,
                prefer_draft_status=quality == PrdQuality.DRAFT,
            )
            session.extracted_facts = interactive_snapshot["facts"]
            missing_information = interactive_snapshot["missing_information"]
            can_generate_draft = bool(interactive_snapshot["can_generate_draft"])
            can_generate_final = bool(interactive_snapshot["can_generate_final"])
            if quality == PrdQuality.DRAFT and not can_generate_draft:
                raise InsufficientFactsError(
                    "Interactive draft generation requires minimum facts.",
                    {"missing_information": missing_information, "session_id": session.session_id},
                )
            if quality == PrdQuality.FINAL and not can_generate_final:
                raise InsufficientFactsError(
                    "Interactive final generation requires all required facts.",
                    {"missing_information": missing_information, "session_id": session.session_id},
                )
            markdown = self._llm_provider.draft_prd_from_facts(
                facts=session.extracted_facts,
                project_context=session.project_context,
                quality=quality,
            )
            return PrdGenerateResponse(
                mode=session.mode,
                markdown=markdown,
                missing_information=missing_information,
                status=interactive_snapshot["status"].value,
                quality=quality,
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
                quality=None,
            )
        raise UnsupportedModeError(f"Unsupported session mode: {session.mode}")

    def _generate_one_shot(
        self,
        *,
        mode: SessionMode,
        input_text: str,
        project_context: Optional[str],
        quality: Optional[PrdQuality],
    ) -> PrdGenerateResponse:
        """中文说明：基于 one-shot 输入生成 PRD。

        输入：模式、输入文本、项目上下文、请求质量档位。
        输出：PRD 生成结果。
        关键逻辑：interactive 先抽取并合并 facts，再按 draft/final 判定；reverse 忽略 quality。
        """

        if mode == SessionMode.INTERACTIVE:
            requested_quality = quality or PrdQuality.FINAL
            extraction = self._llm_provider.extract_facts_from_turn(
                existing_facts=ExtractedFacts(),
                input_text=input_text,
                project_context=project_context,
            )
            interactive_snapshot = self._build_interactive_snapshot(
                facts=extraction.merged_facts,
                project_context=project_context,
                open_questions=extraction.open_questions,
                prefer_draft_status=requested_quality == PrdQuality.DRAFT,
            )
            facts = interactive_snapshot["facts"]
            can_generate_draft = interactive_snapshot["can_generate_draft"]
            can_generate_final = interactive_snapshot["can_generate_final"]
            missing_information = interactive_snapshot["missing_information"]
            if requested_quality == PrdQuality.DRAFT and not can_generate_draft:
                raise InsufficientFactsError(
                    "Interactive one-shot draft generation requires minimum facts.",
                    {"missing_information": missing_information},
                )
            if requested_quality == PrdQuality.FINAL and not can_generate_final:
                raise InsufficientFactsError(
                    "Interactive one-shot final generation requires all required facts.",
                    {"missing_information": missing_information},
                )
            markdown = self._llm_provider.draft_prd_from_facts(
                facts=facts,
                project_context=project_context,
                quality=requested_quality,
            )
            return PrdGenerateResponse(
                mode=mode,
                markdown=markdown,
                missing_information=missing_information,
                status=interactive_snapshot["status"].value,
                quality=requested_quality,
            )

        if mode == SessionMode.REVERSE:
            prompt = build_reverse_prd_prompt(input_text, project_context)
            missing_information = self._missing_reverse_information(input_text)
            return PrdGenerateResponse(
                mode=mode,
                markdown=self._llm_provider.generate(prompt),
                missing_information=missing_information,
                status="generated_with_gaps" if missing_information else "generated",
                quality=None,
            )
        raise UnsupportedModeError(f"Unsupported session mode: {mode}")

    def _build_initial_extraction(
        self, session: SessionState, input_text: Optional[str]
    ) -> Optional[FactExtractionResult]:
        """中文说明：为 session start 构造初始抽取结果。

        输入：当前 session、可选首轮输入。
        输出：interactive 下的抽取结果，reverse 下返回 `None`。
        关键逻辑：即使没有输入，也为 interactive 生成初始 open questions。
        """

        if session.mode != SessionMode.INTERACTIVE:
            return None
        return self._llm_provider.extract_facts_from_turn(
            existing_facts=session.extracted_facts,
            input_text=input_text or "",
            project_context=session.project_context,
        )

    def _extract_session_facts(
        self, session: SessionState, input_text: str
    ) -> Optional[FactExtractionResult]:
        """中文说明：根据当前 session 模式执行事实收敛。

        输入：session、本轮输入。
        输出：interactive 下的抽取结果，reverse 下返回 `None`。
        关键逻辑：reverse 不进入 interactive v2 抽取编排。
        """

        if session.mode != SessionMode.INTERACTIVE:
            return None
        return self._llm_provider.extract_facts_from_turn(
            existing_facts=session.extracted_facts,
            input_text=input_text,
            project_context=session.project_context,
        )

    def _build_session_payload(
        self,
        *,
        session: SessionState,
        extraction: Optional[FactExtractionResult],
    ) -> dict[str, object]:
        """中文说明：构造 session 接口统一响应载荷。

        输入：session、可选的 interactive 抽取结果。
        输出：响应字典。
        关键逻辑：interactive 和 reverse 分开构造，但保持兼容字段齐全。
        """

        if session.mode == SessionMode.INTERACTIVE:
            facts, open_questions = self._resolve_interactive_facts_and_questions(
                session=session,
                extraction=extraction,
            )
            interactive_snapshot = self._build_interactive_snapshot(
                facts=facts,
                project_context=session.project_context,
                open_questions=open_questions,
            )
            next_question = self._llm_provider.generate_next_question(
                facts=interactive_snapshot["facts"],
                open_questions=interactive_snapshot["open_questions"],
                project_context=session.project_context,
            )
            # 中文说明：interactive 下 `can_generate` 等价于 `can_generate_final`，
            # 这里保留该字段是为了兼容旧客户端。
            return {
                "session_id": session.session_id,
                "mode": session.mode,
                "turn_count": session.turn_count,
                "extracted_facts": interactive_snapshot["facts"],
                "missing_information": interactive_snapshot["missing_information"],
                "can_generate": interactive_snapshot["can_generate_final"],
                "can_generate_draft": interactive_snapshot["can_generate_draft"],
                "can_generate_final": interactive_snapshot["can_generate_final"],
                "open_questions": interactive_snapshot["open_questions"],
                "next_prompt": render_next_prompt(next_question),
                "status": interactive_snapshot["status"].value,
            }

        reverse_missing = self._missing_reverse_information(self._collect_user_text(session.messages))
        can_generate = self._can_generate_reverse(session)
        next_prompt = (
            "信息已经足够，可以生成 reverse PRD。"
            if can_generate
            else "请补充更完整的产品摘要，包括目标、用户、场景、核心功能和转化路径。"
        )
        return {
            "session_id": session.session_id,
            "mode": session.mode,
            "turn_count": session.turn_count,
            "extracted_facts": session.extracted_facts,
            "missing_information": reverse_missing,
            "can_generate": can_generate,
            "can_generate_draft": False,
            "can_generate_final": False,
            "open_questions": [],
            "next_prompt": next_prompt,
            "status": "ready" if can_generate else "needs_input",
        }

    def _resolve_interactive_facts_and_questions(
        self,
        *,
        session: SessionState,
        extraction: Optional[FactExtractionResult],
    ) -> tuple[ExtractedFacts, list[OpenQuestion]]:
        """中文说明：统一解析 interactive 的 facts 与结构化 open questions。

        输入：session、可选抽取结果。
        输出：带字符串 open question 摘要的 facts，以及结构化 open questions。
        关键逻辑：保持 `ExtractedFacts.open_questions` 与响应层 `OpenQuestion` 分层职责。
        """

        if extraction is None:
            open_questions = self._rebuild_open_questions(
                facts=session.extracted_facts,
                project_context=session.project_context,
            )
            facts = self._with_open_question_summaries(session.extracted_facts, open_questions)
            return facts, open_questions
        facts = self._with_open_question_summaries(
            extraction.merged_facts,
            extraction.open_questions,
        )
        return facts, extraction.open_questions

    def _with_open_question_summaries(
        self,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
    ) -> ExtractedFacts:
        """中文说明：将结构化 open questions 单向汇总回 facts 字符串摘要。

        输入：facts、结构化 open questions。
        输出：复制后的 facts。
        关键逻辑：只做 service 单向写回，避免结构化对象与字符串表示双向不同步。
        """

        facts_copy = facts.model_copy(deep=True)
        facts_copy.open_questions = [question.question for question in open_questions]
        return facts_copy

    def _rebuild_open_questions(
        self,
        *,
        facts: ExtractedFacts,
        project_context: Optional[str],
    ) -> list[OpenQuestion]:
        """中文说明：基于当前 facts 重建结构化 open questions。

        输入：当前 facts、项目上下文。
        输出：结构化 open questions。
        关键逻辑：当前通过复用 `extract_facts_from_turn(..., input_text="")` 重建 open questions，
        这样可以避免在 service 层重复维护问题规则。
        """

        rebuilt = self._llm_provider.extract_facts_from_turn(
            existing_facts=facts,
            input_text="",
            project_context=project_context,
        )
        return rebuilt.open_questions

    def _build_interactive_snapshot(
        self,
        *,
        facts: ExtractedFacts,
        project_context: Optional[str],
        open_questions: Optional[list[OpenQuestion]] = None,
        prefer_draft_status: bool = False,
    ) -> dict[str, object]:
        """中文说明：统一计算 interactive 当前收敛快照。

        输入：facts、项目上下文、可选结构化 open questions、是否偏向 draft 状态。
        输出：包含 facts、open questions、可生成标记、缺失信息与状态的字典。
        关键逻辑：
        - 让 session 响应和 `/prd/generate` 共用同一套判定，减少分支重复
        - `missing_information` 当前是“缺字段 + 阻塞型问题 key”的并集，不是完整问题列表
        - `reasoning_summary` 仍保留在抽取结果中，当前 service 层未消费，作为后续扩展字段预留
        """

        resolved_open_questions = open_questions or self._rebuild_open_questions(
            facts=facts,
            project_context=project_context,
        )
        resolved_facts = self._with_open_question_summaries(facts, resolved_open_questions)
        can_generate_draft = self._can_generate_interactive_draft(resolved_facts)
        can_generate_final = self._can_generate_interactive_final(
            resolved_facts,
            resolved_open_questions,
        )
        missing_information = self._interactive_missing_information(
            resolved_facts,
            resolved_open_questions,
        )
        status = self._resolve_interactive_state(
            facts=resolved_facts,
            open_questions=resolved_open_questions,
            can_generate_draft=can_generate_draft,
            can_generate_final=can_generate_final,
            prefer_draft_status=prefer_draft_status,
        )
        return {
            "facts": resolved_facts,
            "open_questions": resolved_open_questions,
            "can_generate_draft": can_generate_draft,
            "can_generate_final": can_generate_final,
            "missing_information": missing_information,
            "status": status,
        }

    def _can_generate_interactive_draft(self, facts: ExtractedFacts) -> bool:
        """中文说明：判断 interactive 是否满足 draft 最低门槛。

        输入：当前 facts。
        输出：是否可生成 draft。
        关键逻辑：严格按已固定的五个最小字段进行判定。
        """

        return all(bool(getattr(facts, field_name)) for field_name in DRAFT_REQUIRED_FIELDS)

    def _can_generate_interactive_final(
        self,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
    ) -> bool:
        """中文说明：判断 interactive 是否满足 final 最低门槛。

        输入：当前 facts、结构化 open questions。
        输出：是否可生成 final。
        关键逻辑：在 draft 条件之上，要求 final 必需字段齐全且不存在阻塞问题。
        """

        if not self._can_generate_interactive_draft(facts):
            return False
        if not all(bool(getattr(facts, field_name)) for field_name in FINAL_REQUIRED_FIELDS):
            return False
        return not any(question.blocking for question in open_questions)

    def _interactive_missing_information(
        self,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
    ) -> list[str]:
        """中文说明：汇总 interactive 当前仍缺失的关键信息。

        输入：当前 facts、结构化 open questions。
        输出：稳定字符串列表。
        关键逻辑：当前 `missing_information` 是“缺字段 + 阻塞型问题 key”的并集，
        它不是完整问题列表，而是供兼容接口和错误详情使用的最小缺口摘要。
        """

        missing: list[str] = []
        for field_name in [*DRAFT_REQUIRED_FIELDS, *FINAL_REQUIRED_FIELDS]:
            value = getattr(facts, field_name)
            if not value and field_name not in missing:
                missing.append(field_name)
        for question in open_questions:
            if question.blocking and question.key not in missing:
                missing.append(question.key)
        return missing

    def _resolve_interactive_state(
        self,
        *,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
        can_generate_draft: bool,
        can_generate_final: bool,
        prefer_draft_status: bool = False,
    ) -> InteractiveSessionStatus:
        """中文说明：统一判定 interactive 当前状态。

        输入：facts、open questions、draft/final 可生成标记、是否偏向 draft 状态。
        输出：唯一的 interactive 状态枚举。
        关键逻辑：所有状态判断只从这里产出，避免分散在多个分支里。
        """

        if can_generate_final:
            return InteractiveSessionStatus.READY_FOR_FINAL
        non_blocking_gaps = any(not question.blocking for question in open_questions)
        if can_generate_draft:
            if prefer_draft_status and non_blocking_gaps:
                return InteractiveSessionStatus.DRAFT_WITH_GAPS
            return InteractiveSessionStatus.READY_FOR_DRAFT

        confirmed_count = sum(bool(getattr(facts, field_name)) for field_name in DRAFT_REQUIRED_FIELDS)
        if confirmed_count >= 2 or facts.constraints or facts.success_metrics or facts.platform:
            return InteractiveSessionStatus.CLARIFYING
        return InteractiveSessionStatus.DISCOVERING

    def _summarize_prd(self, prd_markdown: str) -> str:
        """中文说明：抽取 PRD 中的关键信息摘要。

        输入：PRD markdown。
        输出：压缩后的摘要文本。
        关键逻辑：保留标题和前若干关键内容，供任务拆解复用。
        """

        lines = [line.strip() for line in prd_markdown.splitlines() if line.strip()]
        selected_lines: list[str] = []
        for line in lines:
            if line.startswith("# PRD") or line.startswith("## "):
                selected_lines.append(line)
                continue
            if len(selected_lines) >= 14:
                break
            selected_lines.append(line)
        return "\n".join(selected_lines[:14])

    def _build_tasks_markdown(
        self, tasks: list[TaskItem], task_generation_prompt: str, project_name: str
    ) -> str:
        """中文说明：将任务列表渲染为 markdown。

        输入：任务列表、任务生成 prompt、项目名。
        输出：Tasks markdown。
        关键逻辑：保持原有任务输出格式稳定。
        """

        lines = [
            "# Tasks",
            "## Project",
            project_name,
            "## Summary",
            task_generation_prompt,
            "## Task List",
        ]
        for index, task in enumerate(tasks, start=1):
            lines.extend(
                [
                    f"### {index}. {task.title}",
                    f"- Category: {task.category}",
                    f"- Priority: {task.priority}",
                    f"- Milestone: {task.milestone}",
                    f"- Objective: {task.objective}",
                    f"- Deliverable: {task.deliverable}",
                ]
            )
        return "\n".join(lines)

    def _extract_prd_sections(self, prd_markdown: str) -> dict[str, str]:
        """中文说明：按二级标题切分 PRD 章节。

        输入：PRD markdown。
        输出：章节名到正文的映射。
        关键逻辑：仅做轻量切分，供任务拆解使用。
        """

        sections: dict[str, list[str]] = {}
        current_section = "root"
        for raw_line in prd_markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("## "):
                current_section = line[3:].strip()
                sections.setdefault(current_section, [])
                continue
            sections.setdefault(current_section, []).append(line)
        return {key: "\n".join(value) for key, value in sections.items()}

    def _build_tasks_from_sections(self, sections: dict[str, str]) -> list[TaskItem]:
        """中文说明：根据 PRD 章节生成 milestone 任务列表。

        输入：PRD 章节映射。
        输出：任务列表。
        关键逻辑：复用现有规则化任务拆解能力。
        """

        tasks: list[TaskItem] = [
            TaskItem(
                title="梳理目标与范围边界",
                category="planning",
                priority="P0",
                milestone="M1-Planning",
                objective="基于背景与目标、用户与场景明确本次交付边界和成功标准。",
                deliverable="形成可执行的范围说明、目标说明和关键场景清单。",
            )
        ]

        if "3. 功能定义" in sections:
            tasks.append(
                TaskItem(
                    title="拆解功能模块与接口边界",
                    category="application",
                    priority="P0",
                    milestone="M2-Core Delivery",
                    objective="将功能定义拆成可交付模块，并明确模块输入输出边界。",
                    deliverable="完成功能模块划分和主接口交互约束。",
                )
            )
        if "4. 用户流程" in sections:
            tasks.append(
                TaskItem(
                    title="实现主流程编排",
                    category="workflow",
                    priority="P0",
                    milestone="M2-Core Delivery",
                    objective="根据用户流程实现关键业务路径和状态流转。",
                    deliverable="交付符合 PRD 主流程的编排逻辑。",
                )
            )
        if "5. 数据模型（逻辑）" in sections:
            tasks.append(
                TaskItem(
                    title="落地逻辑数据模型",
                    category="data",
                    priority="P1",
                    milestone="M2-Core Delivery",
                    objective="根据逻辑数据模型定义核心实体和关键字段。",
                    deliverable="完成实体、状态和关键字段结构设计。",
                )
            )
        if "6. 行为定义" in sections:
            tasks.append(
                TaskItem(
                    title="补齐业务行为约束",
                    category="behavior",
                    priority="P1",
                    milestone="M3-Behavior and Quality",
                    objective="将行为定义转成可执行的业务规则和边界处理。",
                    deliverable="完成主要业务规则、异常路径和状态处理。",
                )
            )
        if "7. 转化路径" in sections:
            tasks.append(
                TaskItem(
                    title="接入转化路径支持",
                    category="conversion",
                    priority="P1",
                    milestone="M3-Behavior and Quality",
                    objective="围绕转化路径补齐关键节点、状态和输出结果。",
                    deliverable="完成转化链路相关流程和输出定义。",
                )
            )
        if "8. 数据埋点（可选）" in sections:
            tasks.append(
                TaskItem(
                    title="补充埋点与验证清单",
                    category="observability",
                    priority="P2",
                    milestone="M4-Verification",
                    objective="根据埋点要求整理观测点和验证检查项。",
                    deliverable="完成埋点事件清单和基础验证方案。",
                )
            )

        tasks.append(
            TaskItem(
                title="整理交付与验证结果",
                category="delivery",
                priority="P0",
                milestone="M4-Verification",
                objective="在全部 milestone 完成后统一整理变更、验证和限制。",
                deliverable="输出 changed files、verification、known limitations。",
            )
        )
        return tasks

    def _collect_milestones(self, tasks: list[TaskItem]) -> list[str]:
        """中文说明：稳定收集去重后的 milestone 列表。

        输入：任务列表。
        输出：有序 milestone 列表。
        关键逻辑：保持首次出现顺序。
        """

        milestones: list[str] = []
        for task in tasks:
            if task.milestone not in milestones:
                milestones.append(task.milestone)
        return milestones

    def _can_generate_reverse(self, session: SessionState) -> bool:
        """中文说明：判断 reverse 会话是否可生成 PRD。

        输入：session。
        输出：是否至少已有用户输入。
        关键逻辑：保持 reverse 的原有最小行为语义。
        """

        return any(message.role == MessageRole.USER for message in session.messages)

    def _missing_reverse_information(self, input_text: str) -> list[str]:
        """中文说明：推断 reverse 输入中缺失的基础信息。

        输入：reverse 汇总文本。
        输出：缺失字段列表。
        关键逻辑：仅做轻量关键词推断，不引入 interactive v2 的事实状态机。
        """

        text = input_text.strip()
        if not text:
            return DRAFT_REQUIRED_FIELDS.copy()

        facts = ExtractedFacts(
            goal=_find_keyword_value(text, ["goal", "目标"]),
            users=_extract_list(text, ["users", "用户"]),
            scenarios=_extract_list(text, ["scenarios", "场景"]),
            core_functions=_extract_list(text, ["core_functions", "核心功能", "functions"]),
            conversion_path=_extract_list(text, ["conversion_path", "转化路径", "conversion"]),
        )
        missing = [field_name for field_name in DRAFT_REQUIRED_FIELDS if not getattr(facts, field_name)]
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

    def _validate_generate_request_shape(self, request: GeneratePrdRequest) -> None:
        """中文说明：校验 `/prd/generate` 的互斥请求 shape。

        输入：PRD 生成请求。
        输出：无返回，非法时抛异常。
        关键逻辑：保持 session-based 与 one-shot 两种调用方式互斥。
        """

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
                "session-based generation accepts session_id and optional quality.",
                {"mode": request.mode, "project_context": request.project_context},
            )
        if has_one_shot_input and request.mode is None:
            raise InvalidRequestShapeError(
                "One-shot generation requires mode + input_text.",
                {"mode": request.mode},
            )

    def _collect_user_text(self, messages: list[Message]) -> str:
        """中文说明：汇总会话中的所有用户输入。

        输入：消息列表。
        输出：拼接后的用户文本。
        关键逻辑：reverse 模式依赖该汇总文本做缺失推断与生成。
        """

        user_messages = [message.content for message in messages if message.role == MessageRole.USER]
        return "\n".join(user_messages)

    def _require_session(self, session_id: str) -> SessionState:
        """中文说明：按 id 获取 session，不存在时抛异常。

        输入：session_id。
        输出：session state。
        关键逻辑：统一缺失会话的错误码与 details。
        """

        session = self._session_store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(
                f"Session '{session_id}' was not found.",
                {"session_id": session_id},
            )
        return session
