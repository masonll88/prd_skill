"""Prompt templates and builders for PRD generation."""

from __future__ import annotations

from typing import Optional

from schemas import ExtractedFacts, SessionMode


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
- “数据模型（逻辑）”只写实体和关键字段
- 不输出 SQL DDL
- 不输出 REST path specs
- “行为定义”只写业务行为，不写技术 API 设计
"""


def build_follow_up_prompt(mode: SessionMode, missing_facts: list[str]) -> str:
    """Build the next assistant prompt for missing facts."""

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
    """Build a prompt for interactive PRD generation."""

    lines = [
        "MODE: interactive",
        PRD_SECTION_TEMPLATE.strip(),
        PRD_CONSTRAINTS.strip(),
        f"GOAL: {facts.goal or ''}",
        f"USERS: {' | '.join(facts.users)}",
        f"SCENARIOS: {' | '.join(facts.scenarios)}",
        f"CORE_FUNCTIONS: {' | '.join(facts.core_functions)}",
        f"CONVERSION_PATH: {' | '.join(facts.conversion_path)}",
        f"PROJECT_CONTEXT: {project_context or ''}",
    ]
    return "\n".join(lines)


def build_reverse_prd_prompt(input_text: str, project_context: Optional[str]) -> str:
    """Build a prompt for reverse PRD generation."""

    lines = [
        "MODE: reverse",
        PRD_SECTION_TEMPLATE.strip(),
        PRD_CONSTRAINTS.strip(),
        f"INPUT_TEXT: {input_text}",
        f"PROJECT_CONTEXT: {project_context or ''}",
    ]
    return "\n".join(lines)


def build_task_generation_prompt(prd_summary: str) -> str:
    """Build a compact prompt describing task decomposition intent."""

    return "\n".join(
        [
            "TASK_MODE: decompose_prd",
            "请基于以下 PRD 摘要拆解实现任务，按业务优先级排序。",
            prd_summary,
        ]
    )


def build_codex_execution_prompt(task_markdown: str) -> str:
    """Build a Codex-oriented execution prompt from generated tasks."""

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
    """Build IMPLEMENT.md-style execution guidance."""

    lines = [
        "# IMPLEMENT",
        f"## Project",
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
