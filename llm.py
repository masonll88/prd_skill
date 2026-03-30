"""LLM abstractions and local provider implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod


def _extract_field(prompt: str, field: str) -> str:
    prefix = f"{field}:"
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _split_items(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


class BaseLLMProvider(ABC):
    """Abstract interface for generating PRD markdown from prompts."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate PRD markdown for the given prompt."""


class StubLLMProvider(BaseLLMProvider):
    """Local deterministic provider used for development and testing."""

    def generate(self, prompt: str) -> str:
        """Generate stable markdown without external model dependencies."""

        mode = _extract_field(prompt, "MODE") or "interactive"
        if mode == "reverse":
            return self._generate_reverse(prompt)
        return self._generate_interactive(prompt)

    def _generate_interactive(self, prompt: str) -> str:
        goal = _extract_field(prompt, "GOAL") or "待补充目标"
        users = _split_items(_extract_field(prompt, "USERS")) or ["待补充用户"]
        scenarios = _split_items(_extract_field(prompt, "SCENARIOS")) or ["待补充场景"]
        functions = _split_items(_extract_field(prompt, "CORE_FUNCTIONS")) or ["待补充功能"]
        conversion = _split_items(_extract_field(prompt, "CONVERSION_PATH")) or ["待补充转化路径"]
        project_context = _extract_field(prompt, "PROJECT_CONTEXT")

        return self._render_prd(
            goal=goal,
            users=users,
            scenarios=scenarios,
            functions=functions,
            conversion_path=conversion,
            project_context=project_context,
            source_summary="基于多轮交互整理出的需求信息。",
        )

    def _generate_reverse(self, prompt: str) -> str:
        summary = _extract_field(prompt, "INPUT_TEXT") or "待补充产品摘要"
        project_context = _extract_field(prompt, "PROJECT_CONTEXT")
        users = ["目标用户"]
        scenarios = ["核心使用场景"]
        functions = ["关键功能点"]
        conversion = ["触达", "激活", "转化"]

        return self._render_prd(
            goal=f"基于摘要沉淀需求，目标为：{summary[:80]}",
            users=users,
            scenarios=scenarios,
            functions=functions,
            conversion_path=conversion,
            project_context=project_context,
            source_summary=summary,
        )

    def _render_prd(
        self,
        *,
        goal: str,
        users: list[str],
        scenarios: list[str],
        functions: list[str],
        conversion_path: list[str],
        project_context: str,
        source_summary: str,
    ) -> str:
        """Render markdown in the exact PRD structure required by the project."""

        user_lines = "\n".join(f"- {item}" for item in users)
        scenario_lines = "\n".join(f"- {item}" for item in scenarios)
        function_lines = "\n".join(f"- {item}" for item in functions)
        flow_lines = "\n".join(
            f"{index}. {item}" for index, item in enumerate(conversion_path, start=1)
        )

        data_entities = [
            "- 用户：用户ID、角色、状态",
            "- 需求会话：session_id、mode、turn_count、更新时间",
            "- PRD草稿：标题、章节内容、生成时间",
        ]
        if project_context:
            data_entities.append("- 项目上下文：上下文摘要、来源说明")
        data_model_lines = "\n".join(data_entities)

        tracking_lines = "\n".join(
            [
                "- 记录 session 创建数",
                "- 记录 PRD 生成成功率",
                "- 记录事实补全轮次",
            ]
        )

        return f"""# PRD
## 1. 背景与目标
{source_summary}

目标：
- {goal}

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
{data_model_lines}

## 6. 行为定义
- 系统支持围绕目标、用户、场景、核心功能和转化路径逐步完善需求。
- 系统在信息不足时提示补充关键业务事实，在信息充分时输出结构化 PRD。
- 系统根据当前模式生成对应的 PRD 草稿，便于继续迭代。

## 7. 转化路径
{flow_lines}

## 8. 数据埋点（可选）
{tracking_lines}
"""
