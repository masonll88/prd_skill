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


def _contains_keyword(items: list[str], keyword: str) -> bool:
    return any(keyword in item for item in items)


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
        scenario_lines = "\n".join(
            f"- {item}：围绕“{goal}”完成关键操作。" for item in scenarios
        )
        function_lines = "\n".join(
            f"- {item}：支撑“{goal}”这一目标的核心业务能力。" for item in functions
        )
        flow_lines = "\n".join(
            f"{index}. {item}" for index, item in enumerate(conversion_path, start=1)
        )

        data_entities = self._build_data_entities(functions)
        data_model_lines = "\n".join(data_entities)
        behavior_lines = self._build_behavior_lines(goal, scenarios, conversion_path)
        tracking_lines = self._build_tracking_lines(conversion_path, functions)
        background_lines = self._build_background_lines(goal, source_summary, project_context)

        return f"""# PRD
## 1. 背景与目标
{background_lines}

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
{behavior_lines}

## 7. 转化路径
{flow_lines}

## 8. 数据埋点（可选）
{tracking_lines}
"""

    def _build_background_lines(
        self, goal: str, source_summary: str, project_context: str
    ) -> str:
        """Build business-oriented background and goal content."""

        lines = [source_summary, "", "目标：", f"- {goal}"]
        if project_context:
            lines.extend(["", f"上下文补充：{project_context}"])
        return "\n".join(lines)

    def _build_data_entities(self, functions: list[str]) -> list[str]:
        """Build logical entities from business functions."""

        entities = ["- 用户：用户ID、角色、状态"]
        if _contains_keyword(functions, "商品"):
            entities.append("- 商品：商品ID、商品名称、商品状态、所属分类")
        if _contains_keyword(functions, "分类"):
            entities.append("- 分类：分类ID、分类名称、排序状态")
        if _contains_keyword(functions, "分享"):
            entities.append("- 分享记录：分享ID、分享用户、分享渠道、转化结果")
        if len(entities) == 1:
            entities.append("- 业务对象：对象ID、对象名称、对象状态、关键属性")
        return entities

    def _build_behavior_lines(
        self, goal: str, scenarios: list[str], conversion_path: list[str]
    ) -> str:
        """Build user-oriented business behavior lines."""

        lines: list[str] = []
        for scenario in scenarios:
            lines.append(f"- 用户在“{scenario}”场景下，为了“{goal}”执行对应业务操作。")
        for step in conversion_path:
            lines.append(f"- 用户在“{step}”节点完成推进，并进入下一步转化阶段。")
        return "\n".join(lines)

    def _build_tracking_lines(
        self, conversion_path: list[str], functions: list[str]
    ) -> str:
        """Build optional tracking suggestions from business flow."""

        lines = [f"- 记录用户在“{step}”节点的转化情况" for step in conversion_path]
        if _contains_keyword(functions, "分享"):
            lines.append("- 记录分享行为的渠道分布与分享后转化结果")
        if not lines:
            lines.append("- 记录关键业务动作的完成情况")
        return "\n".join(lines)
