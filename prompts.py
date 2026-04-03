"""prd_skill 的 prompt 模板与构造器。

中文说明：
- 本文件按职责拆分 interactive v2 的事实抽取、追问生成和 PRD 生成 prompt
- prompt 只负责表达任务约束，不承载业务编排逻辑
- draft 与 final 的输出要求在这里显式区分，避免 provider 只靠文案差异处理
"""

from __future__ import annotations

from typing import Optional

from schemas import (
    ExtractedFacts,
    NextQuestionResult,
    OpenQuestion,
    PrdQuality,
    SessionMode,
)


PRD_SECTION_TEMPLATE = """# PRD
## 1. 背景与目标
## 2. 用户与场景
## 3. 功能定义
## 4. 用户流程
## 5. 数据模型（逻辑）
## 6. 行为定义
## 7. 转化路径
## 8. 数据埋点（可选）
"""


PRD_CONSTRAINTS = """约束：
- 严格输出上述章节，且顺序不能变
- 缺失信息必须明确标注“待补充”
- 不得伪造用户未提供或未确认的事实
- “数据模型（逻辑）”只写实体和关键字段
- 不输出 SQL DDL
- 不输出 REST path specs
- “行为定义”只写业务行为，不写技术 API 设计
"""


def build_facts_extraction_prompt(
    *,
    existing_facts: ExtractedFacts,
    input_text: str,
    project_context: Optional[str],
) -> str:
    """中文说明：构造事实抽取 prompt。

    输入：已有 facts、本轮用户输入、项目上下文。
    输出：用于事实抽取的 prompt 字符串。
    关键逻辑：强调只合并可确认事实，并输出结构化 open questions。
    """

    lines = [
        "TASK: extract_facts_from_turn",
        "请从本轮输入中抽取并合并 interactive v2 所需 facts。",
        "要求：",
        "- merged_facts 必须是完整结构",
        "- open_questions 按优先级排序，阻塞问题在前",
        "- 不要编造用户未明确说明的事实",
        "- 标量字段本轮明确则覆盖，否则保留旧值",
        "- 列表字段做追加去重，不要因本轮未提及而清空",
        "EXISTING_FACTS:",
        existing_facts.model_dump_json(exclude_none=True),
        "INPUT_TEXT:",
        input_text,
        f"PROJECT_CONTEXT: {project_context or ''}",
    ]
    return "\n".join(lines)


def build_next_question_prompt(
    *,
    facts: ExtractedFacts,
    open_questions: list[OpenQuestion],
    project_context: Optional[str],
) -> str:
    """中文说明：构造下一轮追问 prompt。

    输入：当前 facts、结构化 open questions、项目上下文。
    输出：用于生成下一问的 prompt 字符串。
    关键逻辑：限制默认只输出 1 个主问题，最多附带 1 个补充问题。
    """

    lines = [
        "TASK: generate_next_question",
        "请基于当前需求收敛状态生成下一轮追问。",
        "要求：",
        "- 默认只返回 1 个主问题",
        "- 最多附带 1 个补充问题",
        "- 若存在阻塞问题，主问题必须优先针对最高优先级阻塞项",
        "- 补充问题只能用于补强同主题边界或一个强相关关键缺口",
        "- 不要原样返回 open_questions 列表",
        "- 只输出筛选后的主问题和可选补充问题",
        "FACTS:",
        facts.model_dump_json(exclude_none=True),
        "OPEN_QUESTIONS:",
        "["
        + ", ".join(question.model_dump_json(exclude_none=True) for question in open_questions)
        + "]",
        f"PROJECT_CONTEXT: {project_context or ''}",
    ]
    return "\n".join(lines)


def build_prd_drafting_prompt(
    *,
    facts: ExtractedFacts,
    project_context: Optional[str],
    quality: PrdQuality,
) -> str:
    """中文说明：构造 PRD 生成 prompt。

    输入：facts、项目上下文、质量档位。
    输出：用于 PRD 生成的 prompt 字符串。
    关键逻辑：继续强约束章节结构，并要求缺失信息写“待补充”。
    """

    lines = [
        "TASK: draft_prd_from_facts",
        "MODE: interactive",
        f"QUALITY: {quality.value}",
        PRD_SECTION_TEMPLATE.strip(),
        PRD_CONSTRAINTS.strip(),
        (
            "DRAFTING_REQUIREMENT: 这是 draft，允许保留待补充信息，并突出待确认事项。"
            if quality == PrdQuality.DRAFT
            else (
                "DRAFTING_REQUIREMENT: 这是 final，必须把已确认事实组织成可交付版本；"
                "每个章节都要直接给出明确业务结论；"
                "场景、功能、流程、指标之间要保持前后一致；"
                "不得输出“候选”“可能”“建议补充后再定”这类草稿措辞；"
                "仅对缺失事实使用“待补充”。"
            )
        ),
        f"GOAL: {facts.goal or ''}",
        f"USERS: {' | '.join(facts.users)}",
        f"SCENARIOS: {' | '.join(facts.scenarios)}",
        f"CORE_FUNCTIONS: {' | '.join(facts.core_functions)}",
        f"CONVERSION_PATH: {' | '.join(facts.conversion_path)}",
        f"CONSTRAINTS: {' | '.join(facts.constraints)}",
        f"NON_GOALS: {' | '.join(facts.non_goals)}",
        f"DATA_ENTITIES: {' | '.join(facts.data_entities)}",
        f"SUCCESS_METRICS: {' | '.join(facts.success_metrics)}",
        f"PLATFORM: {facts.platform or ''}",
        f"DELIVERY_SCOPE: {' | '.join(facts.delivery_scope)}",
        f"ASSUMPTIONS: {' | '.join(facts.assumptions)}",
        f"RISKS: {' | '.join(facts.risks)}",
        f"OPEN_QUESTIONS: {' | '.join(facts.open_questions)}",
        f"PROJECT_CONTEXT: {project_context or ''}",
    ]
    return "\n".join(lines)


def build_follow_up_prompt(mode: SessionMode, missing_facts: list[str]) -> str:
    """中文说明：兼容旧逻辑的追问文本构造函数。

    输入：session 模式、缺失字段列表。
    输出：追问字符串。
    关键逻辑：在新 service 接管前保留原有简化行为。
    """

    if mode == SessionMode.REVERSE:
        return "请补充更完整的产品摘要，包括目标、用户、场景、核心功能和转化路径。"
    if not missing_facts:
        return "信息已经足够，可以生成 PRD。"
    return (
        "为了继续完善 PRD，请补充这些信息："
        + "、".join(missing_facts)
        + "。请尽量用明确的业务描述回答。"
    )


def build_interactive_prd_prompt(
    facts: ExtractedFacts,
    project_context: Optional[str],
) -> str:
    """中文说明：兼容旧接口的 interactive PRD prompt 构造函数。

    输入：facts、项目上下文。
    输出：旧版 prompt 字符串。
    关键逻辑：这是兼容旧接口的过渡层；新逻辑应优先直接使用 `build_prd_drafting_prompt(...)`。
    """

    return build_prd_drafting_prompt(
        facts=facts,
        project_context=project_context,
        quality=PrdQuality.DRAFT,
    )


def build_reverse_prd_prompt(input_text: str, project_context: Optional[str]) -> str:
    """中文说明：构造 reverse PRD 生成 prompt。

    输入：输入文本、项目上下文。
    输出：reverse prompt 字符串。
    关键逻辑：保持 reverse 的现有边界，不引入 interactive 特有约束。
    """

    lines = [
        "MODE: reverse",
        PRD_SECTION_TEMPLATE.strip(),
        PRD_CONSTRAINTS.strip(),
        f"INPUT_TEXT: {input_text}",
        f"PROJECT_CONTEXT: {project_context or ''}",
    ]
    return "\n".join(lines)


def render_next_prompt(next_question: NextQuestionResult) -> str:
    """中文说明：将结构化问题结果渲染为最终响应文本。

    输入：结构化下一问结果。
    输出：接口返回给客户端的追问文本。
    关键逻辑：在 prompt 层内部完成渲染，避免反向依赖 llm 层私有函数。
    """

    if next_question.secondary_question:
        return (
            f"主问题：{next_question.primary_question}\n"
            f"补充问题：{next_question.secondary_question}"
        )
    return next_question.primary_question


def build_task_generation_prompt(prd_summary: str) -> str:
    """中文说明：构造任务拆解 prompt。

    输入：PRD 摘要。
    输出：任务拆解 prompt 字符串。
    关键逻辑：保持现有任务生成能力不受本次 interactive v2 改造影响。
    """

    return "\n".join(
        [
            "TASK_MODE: decompose_prd",
            "请基于以下 PRD 摘要拆解实现任务，按业务优先级排序。",
            prd_summary,
        ]
    )


def build_codex_execution_prompt(task_markdown: str) -> str:
    """中文说明：构造 Codex 执行提示。

    输入：任务 markdown。
    输出：用于 Codex 执行的 prompt 字符串。
    关键逻辑：保持现有 milestone 驱动的执行习惯不变。
    """

    return "\n".join(
        [
            "请先阅读 AGENTS.md、PRD.md、TASKS.md、IMPLEMENT.md。",
            "先输出计划，不要立即编码。",
            "按 milestone 顺序实施，不要扩展范围。",
            "每完成一个 milestone 后先运行验证，再继续下一个 milestone。",
            "全部完成后输出 changed files / verification / known limitations。",
            "",
            task_markdown,
        ]
    )


def build_implement_markdown(
    project_name: str,
    milestones: list[str],
    project_context: Optional[str],
) -> str:
    """中文说明：构造 IMPLEMENT 风格的执行说明。

    输入：项目名、milestones、项目上下文。
    输出：IMPLEMENT markdown。
    关键逻辑：保持原有任务拆解能力与文档格式兼容。
    """

    lines = [
        "# IMPLEMENT",
        "## Project",
        project_name,
        "## Workflow",
        "1. 先阅读 AGENTS.md、PRD.md、TASKS.md、IMPLEMENT.md。",
        "2. 先输出实现计划，不要立即编码。",
        "3. 按 milestone 顺序实施。",
        "4. 每个 milestone 后运行验证。",
        "5. 最后输出 changed files / verification / known limitations。",
        "## Milestones",
    ]
    for index, milestone in enumerate(milestones, start=1):
        lines.append(f"{index}. {milestone}")
    if project_context:
        lines.extend(["## Project Context", project_context])
    return "\n".join(lines)
