"""prd_skill 的 LLM 抽象与 provider 实现。

中文说明：
- 本文件定义 interactive v2 所需的能力接口，而不是单一 `generate(prompt)`
- Stub provider 提供本地可运行实现，保证 interactive v2 在无外部模型时也能联调
- OpenAI-compatible provider 当前只提供可扩展骨架，不绑定具体厂商
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from typing import Optional

from schemas import (
    ExtractedFacts,
    FactExtractionResult,
    NextQuestionResult,
    OpenQuestion,
    PrdQuality,
)


@dataclass(frozen=True)
class _QuestionDefinition:
    """中文说明：定义一个标准化追问模板。

    输入：字段键名、字段文案、问题文本、是否阻塞。
    输出：可复用的追问定义对象。
    关键逻辑：用于统一生成 open questions 与下一轮问题。
    """

    key: str
    label: str
    question: str
    blocking: bool


QUESTION_DEFINITIONS = [
    _QuestionDefinition("goal", "产品目标", "这个需求最想解决的核心问题是什么？你希望最终达成什么业务结果？", True),
    _QuestionDefinition("users", "目标用户", "这个产品主要面向哪些用户角色？他们分别要完成什么任务？", True),
    _QuestionDefinition("scenarios", "核心场景", "用户最核心的使用场景是什么？请给出 1 到 3 个高频场景。", True),
    _QuestionDefinition("core_functions", "核心功能", "要支撑这些场景，产品必须具备哪些核心功能？", True),
    _QuestionDefinition("platform", "平台形态", "这个产品优先落在哪个平台？例如 Web、H5、小程序或 App。", True),
    _QuestionDefinition("delivery_scope", "交付范围", "这一期准备实际交付哪些范围？哪些内容明确不在本期内？", True),
    _QuestionDefinition("success_metrics", "成功指标", "你希望上线后用哪些指标判断它是否成功？", True),
    _QuestionDefinition("constraints", "约束条件", "当前有哪些必须遵守的业务、时间、资源或合规约束？", False),
    _QuestionDefinition("non_goals", "非目标", "这次明确不解决什么问题，或者哪些能力先不做？", False),
    _QuestionDefinition("data_entities", "数据实体", "这个需求会涉及哪些关键数据对象或业务实体？", False),
    _QuestionDefinition("assumptions", "前置假设", "目前有哪些默认假设成立，后续如果不成立会影响方案？", False),
    _QuestionDefinition("risks", "风险点", "你现在最担心的风险或不确定性是什么？", False),
]


RELATED_QUESTION_KEYS = {
    "goal": ["users", "success_metrics"],
    "users": ["scenarios", "goal"],
    "scenarios": ["core_functions", "users"],
    "core_functions": ["scenarios", "delivery_scope"],
    "platform": ["delivery_scope", "constraints"],
    "delivery_scope": ["non_goals", "constraints"],
    "success_metrics": ["goal", "delivery_scope"],
    "constraints": ["delivery_scope", "platform"],
    "non_goals": ["delivery_scope", "core_functions"],
    "data_entities": ["core_functions", "scenarios"],
    "assumptions": ["risks", "constraints"],
    "risks": ["assumptions", "constraints"],
}


def _extract_field(prompt: str, field: str) -> str:
    """中文说明：从兼容 prompt 中按字段名前缀提取值。

    输入：prompt 文本、字段名。
    输出：字段值字符串，未找到时返回空串。
    关键逻辑：保留旧版 `generate(prompt)` 的兼容解析能力。
    """

    prefix = f"{field}:"
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _split_items(value: str) -> list[str]:
    """中文说明：将多值字符串拆分为去空白列表。

    输入：使用 `|`、换行或常见分隔符拼接的字符串。
    输出：去重前的字符串列表。
    关键逻辑：兼容 stub prompt 解析与用户输入抽取。
    """

    if not value:
        return []
    items = re.split(r"[\n|,;、]+", value)
    return [item.strip(" -") for item in items if item.strip(" -")]


def _dedupe_items(items: list[str]) -> list[str]:
    """中文说明：对列表字段做稳定去重。

    输入：字符串列表。
    输出：保留原始顺序的去重列表。
    关键逻辑：interactive v2 的列表事实合并采用追加去重，不做整体替换。
    """

    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _contains_keyword(items: list[str], keyword: str) -> bool:
    """中文说明：检查列表中是否包含某个关键词。

    输入：字符串列表、关键词。
    输出：是否命中关键词。
    关键逻辑：用于 stub 生成更贴近业务的逻辑实体与埋点建议。
    """

    return any(keyword in item for item in items)


def _find_keyword_value(text: str, keywords: list[str]) -> Optional[str]:
    """中文说明：从用户输入中按关键词前缀提取单值字段。

    输入：原始文本、可匹配的关键词列表。
    输出：提取到的字段值，未找到时返回 `None`。
    关键逻辑：支持中英文关键词与中英文冒号。
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
    """中文说明：从用户输入中提取列表字段。

    输入：原始文本、可匹配的关键词列表。
    输出：列表字段值。
    关键逻辑：先匹配整行，再按常见分隔符拆分。
    """

    value = _find_keyword_value(text, keywords)
    return _split_items(value) if value else []


def _merge_scalar(existing: Optional[str], incoming: Optional[str]) -> Optional[str]:
    """中文说明：按 interactive v2 规则合并标量字段。

    输入：旧值、新值。
    输出：优先采用本轮明确新值，否则保留旧值。
    关键逻辑：本轮未提及时不清空已有事实。
    """

    return incoming or existing


def _merge_list(existing: list[str], incoming: list[str]) -> list[str]:
    """中文说明：按 interactive v2 规则合并列表字段。

    输入：旧列表、新列表。
    输出：追加去重后的稳定列表。
    关键逻辑：不支持显式整表替换，仅做保守合并。
    """

    return _dedupe_items([*existing, *incoming])


def _render_question_text(result: NextQuestionResult) -> str:
    """中文说明：将结构化下一问渲染为响应字符串。

    输入：结构化问题结果。
    输出：适合直接返回给接口调用方的文本问题。
    关键逻辑：保证最多只出现 1 个主问题和 1 个补充问题。
    """

    if result.secondary_question:
        return (
            f"主问题：{result.primary_question}\n"
            f"补充问题：{result.secondary_question}"
        )
    return result.primary_question


def _fallback_goal_from_input(input_text: str) -> Optional[str]:
    """中文说明：从一句话需求中兜底提取初始 goal 候选。

    输入：用户原始输入文本。
    输出：可作为初始 goal 的候选文本，若输入为空则返回 `None`。
    关键逻辑：当未显式识别出 goal 时，保守地把整句需求作为初始目标候选。
    """

    cleaned = input_text.strip()
    return cleaned or None


class BaseLLMProvider(ABC):
    """中文说明：interactive v2 所需的 LLM 能力接口抽象。"""

    @abstractmethod
    def extract_facts_from_turn(
        self,
        *,
        existing_facts: ExtractedFacts,
        input_text: str,
        project_context: Optional[str],
    ) -> FactExtractionResult:
        """中文说明：从单轮输入中抽取并合并需求事实。

        输入：已有 facts、本轮用户输入、项目上下文。
        输出：包含 merged_facts 与结构化 open questions 的抽取结果。
        关键逻辑：只合并用户明确提供的信息，不凭空编造事实。
        """

    @abstractmethod
    def generate_next_question(
        self,
        *,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
        project_context: Optional[str],
    ) -> NextQuestionResult:
        """中文说明：基于当前 facts 与 open questions 生成下一轮追问。

        输入：当前 facts、结构化 open questions、项目上下文。
        输出：最多 1 个主问题和 1 个补充问题。
        关键逻辑：优先询问最高优先级阻塞问题，避免输出问题列表。
        """

    @abstractmethod
    def draft_prd_from_facts(
        self,
        *,
        facts: ExtractedFacts,
        project_context: Optional[str],
        quality: PrdQuality,
    ) -> str:
        """中文说明：基于收敛后的 facts 生成 PRD markdown。

        输入：facts、项目上下文、目标质量档位。
        输出：严格符合固定章节结构的 markdown。
        关键逻辑：对缺失信息明确标注“待补充”，不伪造事实。
        """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """中文说明：兼容旧接口生成 markdown。

        输入：兼容旧版的 prompt 字符串。
        输出：生成的 markdown。
        关键逻辑：作为过渡层保留，避免 service 重构前仓库失效。
        """


class StubLLMProvider(BaseLLMProvider):
    """中文说明：本地确定性 Stub provider，用于开发与测试。"""

    def extract_facts_from_turn(
        self,
        *,
        existing_facts: ExtractedFacts,
        input_text: str,
        project_context: Optional[str],
    ) -> FactExtractionResult:
        """中文说明：使用规则方式提取并合并 interactive v2 facts。

        输入：已有 facts、本轮用户输入、项目上下文。
        输出：包含 merged_facts、open questions 与确认字段的结果。
        关键逻辑：采用显式关键词抽取与保守合并，保证结果稳定可测试。
        """

        parsed_goal = _find_keyword_value(input_text, ["goal", "目标"])
        if parsed_goal is None and input_text.strip():
            parsed_goal = _fallback_goal_from_input(input_text)
        parsed_platform = _find_keyword_value(input_text, ["platform", "平台", "端"])
        parsed_users = _extract_list(input_text, ["users", "用户"])
        parsed_scenarios = _extract_list(input_text, ["scenarios", "场景"])
        parsed_functions = _extract_list(input_text, ["core_functions", "核心功能", "functions"])
        parsed_conversion = _extract_list(
            input_text, ["conversion_path", "转化路径", "conversion"]
        )
        parsed_constraints = _extract_list(input_text, ["constraints", "约束", "限制"])
        parsed_non_goals = _extract_list(input_text, ["non_goals", "非目标", "不做"])
        parsed_entities = _extract_list(input_text, ["data_entities", "数据实体", "实体"])
        parsed_metrics = _extract_list(input_text, ["success_metrics", "成功指标", "指标"])
        parsed_scope = _extract_list(input_text, ["delivery_scope", "交付范围", "范围"])
        parsed_assumptions = _extract_list(input_text, ["assumptions", "假设"])
        parsed_risks = _extract_list(input_text, ["risks", "风险"])

        merged_facts = ExtractedFacts(
            goal=_merge_scalar(existing_facts.goal, parsed_goal),
            users=_merge_list(existing_facts.users, parsed_users),
            scenarios=_merge_list(existing_facts.scenarios, parsed_scenarios),
            core_functions=_merge_list(existing_facts.core_functions, parsed_functions),
            conversion_path=_merge_list(existing_facts.conversion_path, parsed_conversion),
            constraints=_merge_list(existing_facts.constraints, parsed_constraints),
            non_goals=_merge_list(existing_facts.non_goals, parsed_non_goals),
            data_entities=_merge_list(existing_facts.data_entities, parsed_entities),
            success_metrics=_merge_list(existing_facts.success_metrics, parsed_metrics),
            platform=_merge_scalar(existing_facts.platform, parsed_platform),
            delivery_scope=_merge_list(existing_facts.delivery_scope, parsed_scope),
            assumptions=_merge_list(existing_facts.assumptions, parsed_assumptions),
            open_questions=list(existing_facts.open_questions),
            risks=_merge_list(existing_facts.risks, parsed_risks),
        )

        open_questions = self._build_open_questions(merged_facts)
        newly_confirmed_fields = self._collect_newly_confirmed_fields(
            existing_facts=existing_facts,
            merged_facts=merged_facts,
        )
        reasoning_summary = self._build_reasoning_summary(
            merged_facts=merged_facts,
            newly_confirmed_fields=newly_confirmed_fields,
            open_questions=open_questions,
            project_context=project_context,
        )
        return FactExtractionResult(
            merged_facts=merged_facts,
            open_questions=open_questions,
            newly_confirmed_fields=newly_confirmed_fields,
            conflicts=[],
            reasoning_summary=reasoning_summary,
        )

    def generate_next_question(
        self,
        *,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
        project_context: Optional[str],
    ) -> NextQuestionResult:
        """中文说明：根据优先级生成最多两个问题的下一轮访谈问题。

        输入：当前 facts、结构化 open questions、项目上下文。
        输出：主问题和可选补充问题。
        关键逻辑：先问最高优先级阻塞问题，再决定是否补一个强相关追问。
        """

        if not open_questions:
            return NextQuestionResult(
                primary_question="关键信息已经足够，我可以开始整理 PRD。若你愿意，也可以补充你最担心的风险或限制。",
                secondary_question=None,
                question_count=1,
            )

        primary_item = open_questions[0]
        primary = primary_item.question
        secondary: Optional[str] = None
        related_keys = RELATED_QUESTION_KEYS.get(primary_item.key, [])
        for related_key in related_keys:
            related_item = next(
                (question for question in open_questions[1:] if question.key == related_key),
                None,
            )
            if related_item is not None:
                secondary = related_item.question
                break
        if project_context and "平台" in primary and secondary is None:
            secondary = "如果现有项目上下文里已经有既定技术边界，也可以一并说明。"

        return NextQuestionResult(
            primary_question=primary,
            secondary_question=secondary,
            question_count=2 if secondary else 1,
        )

    def draft_prd_from_facts(
        self,
        *,
        facts: ExtractedFacts,
        project_context: Optional[str],
        quality: PrdQuality,
    ) -> str:
        """中文说明：基于 facts 渲染固定章节结构的 PRD。

        输入：facts、项目上下文、质量档位。
        输出：符合项目既定章节结构的 markdown。
        关键逻辑：无论 draft 还是 final，缺失信息都显式写“待补充”。
        """

        goal = facts.goal or "待补充"
        users = facts.users or ["待补充"]
        scenarios = facts.scenarios or ["待补充"]
        functions = facts.core_functions or ["待补充"]
        conversion_path = facts.conversion_path or ["待补充"]
        constraints = facts.constraints or ["待补充"]
        non_goals = facts.non_goals or ["待补充"]
        data_entities = facts.data_entities or self._build_data_entities(functions)
        success_metrics = facts.success_metrics or ["待补充"]
        delivery_scope = facts.delivery_scope or ["待补充"]
        assumptions = facts.assumptions or ["待补充"]
        risks = facts.risks or ["待补充"]
        platform = facts.platform or "待补充"

        source_summary = (
            "基于 interactive v2 多轮访谈收敛出的需求事实。"
            if quality == PrdQuality.FINAL
            else "基于当前访谈事实生成的 PRD 草稿，缺失信息已显式标注待补充。"
        )

        user_lines = "\n".join(f"- {item}" for item in users)
        scenario_lines = "\n".join(f"- {item}" for item in scenarios)
        function_lines = "\n".join(f"- {item}" for item in functions)
        flow_lines = "\n".join(
            f"{index}. {item}" for index, item in enumerate(conversion_path, start=1)
        )
        entity_lines = "\n".join(f"- {item}" for item in data_entities)
        metric_lines = "\n".join(f"- {item}" for item in success_metrics)
        constraint_lines = "\n".join(f"- {item}" for item in constraints)
        scope_lines = "\n".join(f"- {item}" for item in delivery_scope)
        non_goal_lines = "\n".join(f"- {item}" for item in non_goals)
        assumption_lines = "\n".join(f"- {item}" for item in assumptions)
        risk_lines = "\n".join(f"- {item}" for item in risks)
        behavior_lines = self._build_behavior_lines(goal, scenarios, conversion_path, quality)
        tracking_lines = self._build_tracking_lines(conversion_path, functions, quality)
        pending_lines = "\n".join(f"- {item}" for item in (facts.open_questions or ["待补充"]))

        if quality == PrdQuality.FINAL:
            scenario_lines = "\n".join(
                f"- {item}：围绕“{goal}”完成关键业务动作。"
                for item in scenarios
            )
            function_lines = "\n".join(
                f"- {item}：用于支撑“{goal}”并服务于 {platform} 场景。"
                for item in functions
            )
        else:
            scenario_lines = "\n".join(f"- {item}" for item in scenarios)
            function_lines = "\n".join(f"- {item}" for item in functions)

        return f"""# PRD
## 1. 背景与目标
{source_summary}

目标：
- {goal}

平台：
- {platform}

交付范围：
{scope_lines}

约束条件：
{constraint_lines}

非目标：
{non_goal_lines}

## 2. 用户与场景
用户：
{user_lines}

场景：
{scenario_lines}

## 3. 功能定义
{function_lines}

## 4. 用户流程
{flow_lines}

## 5. 数据模型（逻辑）
{entity_lines}

## 6. 行为定义
{behavior_lines}

前置假设：
{assumption_lines}

风险：
{risk_lines}

待确认事项：
{pending_lines}

## 7. 转化路径
{flow_lines}

成功指标：
{metric_lines}

## 8. 数据埋点（可选）
{tracking_lines}
""" + (f"\n项目上下文：\n- {project_context}\n" if project_context else "")

    def generate(self, prompt: str) -> str:
        """中文说明：兼容旧接口，根据 prompt 生成 markdown。

        输入：兼容旧版约定的 prompt 文本。
        输出：PRD markdown。
        关键逻辑：reverse 仍按旧模式处理，interactive 转为 v2 的 draft 渲染。
        """

        mode = _extract_field(prompt, "MODE") or "interactive"
        if mode == "reverse":
            return self._generate_reverse(prompt)

        facts = ExtractedFacts(
            goal=_extract_field(prompt, "GOAL") or None,
            users=_split_items(_extract_field(prompt, "USERS")),
            scenarios=_split_items(_extract_field(prompt, "SCENARIOS")),
            core_functions=_split_items(_extract_field(prompt, "CORE_FUNCTIONS")),
            conversion_path=_split_items(_extract_field(prompt, "CONVERSION_PATH")),
            constraints=_split_items(_extract_field(prompt, "CONSTRAINTS")),
            non_goals=_split_items(_extract_field(prompt, "NON_GOALS")),
            data_entities=_split_items(_extract_field(prompt, "DATA_ENTITIES")),
            success_metrics=_split_items(_extract_field(prompt, "SUCCESS_METRICS")),
            platform=_extract_field(prompt, "PLATFORM") or None,
            delivery_scope=_split_items(_extract_field(prompt, "DELIVERY_SCOPE")),
            assumptions=_split_items(_extract_field(prompt, "ASSUMPTIONS")),
            risks=_split_items(_extract_field(prompt, "RISKS")),
            open_questions=_split_items(_extract_field(prompt, "OPEN_QUESTIONS")),
        )
        quality = PrdQuality(_extract_field(prompt, "QUALITY") or PrdQuality.DRAFT.value)
        return self.draft_prd_from_facts(
            facts=facts,
            project_context=_extract_field(prompt, "PROJECT_CONTEXT") or None,
            quality=quality,
        )

    def _build_open_questions(self, facts: ExtractedFacts) -> list[OpenQuestion]:
        """中文说明：根据当前 facts 生成结构化未决问题。

        输入：当前 facts。
        输出：按优先级排序、最多 5 条的 open questions。
        关键逻辑：阻塞问题优先，保证 interactive 状态判断可复用。
        """

        questions: list[OpenQuestion] = []
        for definition in QUESTION_DEFINITIONS:
            value = getattr(facts, definition.key)
            is_missing = not value
            if not is_missing:
                continue
            questions.append(
                OpenQuestion(
                    key=definition.key,
                    question=definition.question,
                    blocking=definition.blocking,
                )
            )
        questions.sort(key=lambda item: (not item.blocking, item.key))
        return questions[:5]

    def _collect_newly_confirmed_fields(
        self,
        *,
        existing_facts: ExtractedFacts,
        merged_facts: ExtractedFacts,
    ) -> list[str]:
        """中文说明：识别本轮新确认的字段名。

        输入：旧 facts、合并后的 facts。
        输出：发生新增或补全的字段名列表。
        关键逻辑：用于在 service 层判断本轮是否发生有效收敛。
        """

        field_names: list[str] = []
        for field_name in merged_facts.model_fields:
            previous = getattr(existing_facts, field_name)
            current = getattr(merged_facts, field_name)
            if previous != current and current:
                field_names.append(field_name)
        return field_names

    def _build_reasoning_summary(
        self,
        *,
        merged_facts: ExtractedFacts,
        newly_confirmed_fields: list[str],
        open_questions: list[OpenQuestion],
        project_context: Optional[str],
    ) -> str:
        """中文说明：生成面向编排层的简短收敛摘要。

        输入：合并后的 facts、本轮新确认字段、open questions、项目上下文。
        输出：简短摘要文本。
        关键逻辑：帮助 service 记录当前收敛进度，不直接作为用户可见 PRD 内容。
        """

        confirmed_text = "、".join(newly_confirmed_fields) if newly_confirmed_fields else "暂无新增确认字段"
        pending_text = "、".join(question.key for question in open_questions) or "暂无未决问题"
        context_text = f"；参考上下文：{project_context}" if project_context else ""
        return f"本轮确认：{confirmed_text}；待继续澄清：{pending_text}{context_text}"

    def _generate_reverse(self, prompt: str) -> str:
        """中文说明：兼容 reverse 模式的旧版生成逻辑。

        输入：reverse 模式 prompt。
        输出：固定章节结构的 reverse PRD。
        关键逻辑：保持旧能力边界，不引入 interactive v2 的状态语义。
        """

        summary = _extract_field(prompt, "INPUT_TEXT") or "待补充产品摘要"
        project_context = _extract_field(prompt, "PROJECT_CONTEXT") or None
        facts = ExtractedFacts(
            goal=f"基于摘要沉淀需求，目标为：{summary[:80]}",
            users=["目标用户"],
            scenarios=["核心使用场景"],
            core_functions=["关键功能点"],
            conversion_path=["触达", "激活", "转化"],
            data_entities=["业务对象：对象ID、对象名称、对象状态、关键属性"],
            platform="待补充",
            delivery_scope=["待补充"],
            constraints=["待补充"],
            success_metrics=["待补充"],
            assumptions=["待补充"],
            risks=["待补充"],
            non_goals=["待补充"],
        )
        return self.draft_prd_from_facts(
            facts=facts,
            project_context=project_context,
            quality=PrdQuality.DRAFT,
        )

    def _build_data_entities(self, functions: list[str]) -> list[str]:
        """中文说明：根据核心功能推导逻辑数据实体。

        输入：核心功能列表。
        输出：逻辑实体定义列表。
        关键逻辑：若用户未明确提供实体，则给出保守且通用的占位结构。
        """

        entities = ["用户：用户ID、角色、状态"]
        if _contains_keyword(functions, "商品"):
            entities.append("商品：商品ID、商品名称、商品状态、所属分类")
        if _contains_keyword(functions, "分类"):
            entities.append("分类：分类ID、分类名称、排序状态")
        if _contains_keyword(functions, "分享"):
            entities.append("分享记录：分享ID、分享用户、分享渠道、转化结果")
        if len(entities) == 1:
            entities.append("业务对象：对象ID、对象名称、对象状态、关键属性")
        return entities

    def _build_behavior_lines(
        self,
        goal: str,
        scenarios: list[str],
        conversion_path: list[str],
        quality: PrdQuality,
    ) -> str:
        """中文说明：构造业务行为定义章节内容。

        输入：目标、场景列表、转化路径列表、质量档位。
        输出：行为定义 markdown 文本。
        关键逻辑：final 档位输出更收敛的业务描述，draft 保留更明显的草稿表达。
        """

        lines: list[str] = []
        for scenario in scenarios:
            if quality == PrdQuality.FINAL:
                lines.append(f"- 用户在“{scenario}”场景下，以“{goal}”为目标完成稳定业务闭环。")
            else:
                lines.append(f"- 用户在“{scenario}”场景下，为了“{goal}”执行对应业务操作。")
        for step in conversion_path:
            if quality == PrdQuality.FINAL:
                lines.append(f"- 在“{step}”节点需要有明确输入、输出与结果判断。")
            else:
                lines.append(f"- 用户在“{step}”节点完成推进，并进入下一步转化阶段。")
        if not lines:
            lines.append("- 待补充")
        return "\n".join(lines)

    def _build_tracking_lines(
        self,
        conversion_path: list[str],
        functions: list[str],
        quality: PrdQuality,
    ) -> str:
        """中文说明：构造埋点建议章节内容。

        输入：转化路径列表、功能列表、质量档位。
        输出：埋点建议 markdown 文本。
        关键逻辑：final 档位会更强调结果型观测项，draft 保留草稿式建议。
        """

        if quality == PrdQuality.FINAL:
            lines = [f"- 记录用户在“{step}”节点的进入量、完成量与流失量" for step in conversion_path]
        else:
            lines = [f"- 记录用户在“{step}”节点的转化情况" for step in conversion_path]
        if _contains_keyword(functions, "分享"):
            lines.append("- 记录分享行为的渠道分布与分享后转化结果")
        if not lines:
            lines.append("- 待补充")
        return "\n".join(lines)


class OpenAICompatibleLLMProvider(BaseLLMProvider):
    """中文说明：兼容 OpenAI 风格接口的 provider 骨架。"""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """中文说明：初始化 OpenAI-compatible provider 骨架。

        输入：可选的 base_url、api_key、model。
        输出：provider 实例。
        关键逻辑：当前只固定依赖注入接口，不在此处绑定具体厂商实现。
        """

        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    def extract_facts_from_turn(
        self,
        *,
        existing_facts: ExtractedFacts,
        input_text: str,
        project_context: Optional[str],
    ) -> FactExtractionResult:
        """中文说明：占位的事实抽取接口。

        输入：已有 facts、本轮输入、项目上下文。
        输出：结构化抽取结果。
        关键逻辑：当前提供骨架，待后续接入真实兼容接口。
        """

        raise NotImplementedError("OpenAI-compatible fact extraction is not implemented yet.")

    def generate_next_question(
        self,
        *,
        facts: ExtractedFacts,
        open_questions: list[OpenQuestion],
        project_context: Optional[str],
    ) -> NextQuestionResult:
        """中文说明：占位的下一轮追问接口。

        输入：facts、open questions、项目上下文。
        输出：结构化下一问。
        关键逻辑：当前提供骨架，待后续接入真实兼容接口。
        """

        raise NotImplementedError("OpenAI-compatible next-question generation is not implemented yet.")

    def draft_prd_from_facts(
        self,
        *,
        facts: ExtractedFacts,
        project_context: Optional[str],
        quality: PrdQuality,
    ) -> str:
        """中文说明：占位的 PRD 生成接口。

        输入：facts、项目上下文、质量档位。
        输出：PRD markdown。
        关键逻辑：当前提供骨架，待后续接入真实兼容接口。
        """

        raise NotImplementedError("OpenAI-compatible PRD drafting is not implemented yet.")

    def generate(self, prompt: str) -> str:
        """中文说明：占位的兼容旧接口生成方法。

        输入：旧版 prompt 文本。
        输出：生成结果。
        关键逻辑：当前提供骨架，避免接口缺失。
        """

        raise NotImplementedError("OpenAI-compatible generate(prompt) is not implemented yet.")


__all__ = [
    "BaseLLMProvider",
    "OpenAICompatibleLLMProvider",
    "StubLLMProvider",
    "_render_question_text",
]
