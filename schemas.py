"""prd_skill 的 Pydantic 数据模型定义。

中文说明：
- 本文件集中维护 API 请求/响应模型、枚举和会话状态模型
- interactive v2 相关的 facts、结构化问题和质量档位也统一定义在这里
- 所有接口层与服务层都应复用这里的稳定类型，避免散落定义
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SessionMode(str, Enum):
    """支持的会话模式。"""

    INTERACTIVE = "interactive"
    REVERSE = "reverse"


class MessageRole(str, Enum):
    """支持的消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """会话中存储的一条聊天消息。"""

    role: MessageRole
    content: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PrdQuality(str, Enum):
    """中文说明：交互式产品需求文档生成支持的质量档位。"""

    DRAFT = "draft"
    FINAL = "final"


class InteractiveSessionStatus(str, Enum):
    """中文说明：交互式多轮需求收敛过程中的高层状态。"""

    DISCOVERING = "discovering"
    CLARIFYING = "clarifying"
    READY_FOR_DRAFT = "ready_for_draft"
    READY_FOR_FINAL = "ready_for_final"
    DRAFT_WITH_GAPS = "draft_with_gaps"


class OpenQuestion(BaseModel):
    """中文说明：交互式流程中未决问题的结构化表示。"""

    key: str = Field(min_length=1)
    question: str = Field(min_length=1)
    blocking: bool


class ExtractedFacts(BaseModel):
    """从用户输入中提取出的半结构化事实。"""

    goal: Optional[str] = None
    users: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    core_functions: list[str] = Field(default_factory=list)
    conversion_path: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    data_entities: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    platform: Optional[str] = None
    delivery_scope: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class FactExtractionResult(BaseModel):
    """中文说明：单轮事实抽取与合并后的结构化结果。"""

    merged_facts: ExtractedFacts
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    newly_confirmed_fields: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    reasoning_summary: Optional[str] = None


class NextQuestionResult(BaseModel):
    """中文说明：下一轮追问生成结果。"""

    primary_question: str = Field(min_length=1)
    secondary_question: Optional[str] = None
    question_count: int = Field(ge=1, le=2)

    @model_validator(mode="after")
    def validate_question_consistency(self) -> "NextQuestionResult":
        """中文说明：校验问题数量与补充问题字段的一致性。

        输入：当前 `NextQuestionResult` 实例。
        输出：校验通过后的实例本身。
        关键逻辑：
        - `question_count == 1` 时，`secondary_question` 必须为空
        - `question_count == 2` 时，`secondary_question` 必须非空
        """

        if self.question_count == 1 and self.secondary_question is not None:
            raise ValueError(
                "secondary_question must be None when question_count is 1."
            )
        if self.question_count == 2 and not self.secondary_question:
            raise ValueError(
                "secondary_question is required when question_count is 2."
            )
        return self


class SessionState(BaseModel):
    """活跃产品需求文档会话的持久化状态。"""

    session_id: str
    mode: SessionMode
    messages: list[Message] = Field(default_factory=list)
    extracted_facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    turn_count: int = 0
    project_context: Optional[str] = None


class ErrorResponse(BaseModel):
    """所有接口统一返回的标准错误响应。"""

    error_code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


class SessionStartRequest(BaseModel):
    """启动会话的请求体。"""

    mode: SessionMode
    input_text: Optional[str] = None
    project_context: Optional[str] = None


class SessionContinueRequest(BaseModel):
    """继续已有会话的请求体。"""

    session_id: str = Field(min_length=1)
    input_text: str = Field(min_length=1)


class GeneratePrdRequest(BaseModel):
    """标准化后的 PRD 生成请求。

    该 schema 只负责对可选字符串字段做标准化处理。
    互斥的请求形态约束由 service 层负责校验。
    """

    session_id: Optional[str] = None
    mode: Optional[SessionMode] = None
    input_text: Optional[str] = None
    project_context: Optional[str] = None
    quality: Optional[PrdQuality] = None

    @model_validator(mode="after")
    def normalize_strings(self) -> "GeneratePrdRequest":
        """中文说明：将空白字符串标准化为 `None`。

        输入：当前 `GeneratePrdRequest` 实例。
        输出：标准化后的实例本身。
        关键逻辑：把空串统一转为 `None`，便于 service 层做互斥 shape 校验。
        """

        if self.session_id is not None and not self.session_id.strip():
            self.session_id = None
        if self.input_text is not None and not self.input_text.strip():
            self.input_text = None
        if self.project_context is not None and not self.project_context.strip():
            self.project_context = None
        return self


class SessionStatusResponse(BaseModel):
    """中文说明：会话类接口的共享响应结构。"""

    session_id: str
    mode: SessionMode
    turn_count: int
    extracted_facts: ExtractedFacts
    missing_information: list[str]
    can_generate: bool
    can_generate_draft: bool
    can_generate_final: bool
    open_questions: list[OpenQuestion]
    next_prompt: str
    status: InteractiveSessionStatus | str


class SessionStartResponse(SessionStatusResponse):
    """启动会话时返回的响应。"""


class SessionContinueResponse(SessionStatusResponse):
    """继续会话时返回的响应。"""


class PrdGenerateResponse(BaseModel):
    """生成的产品需求文档标记文本响应。"""

    mode: SessionMode
    markdown: str
    missing_information: list[str]
    status: str
    quality: Optional[PrdQuality] = None


class TaskItem(BaseModel):
    """从产品需求文档拆解出的单个实现任务。"""

    title: str
    category: str
    priority: str
    milestone: str
    objective: str
    deliverable: str


class TasksGenerateRequest(BaseModel):
    """基于产品需求文档标记文本生成任务的请求体。"""

    prd_markdown: str = Field(min_length=1)
    project_name: Optional[str] = None
    mode: Optional[SessionMode] = None
    project_context: Optional[str] = None


class TasksGenerateResponse(BaseModel):
    """包含任务拆解结果与执行提示词的响应。"""

    tasks: list[TaskItem]
    task_markdown: str
    implement_markdown: str
    codex_prompt: str
