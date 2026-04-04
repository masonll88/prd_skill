"""prd_skill 的本地冒烟测试脚本。"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from typing import Iterator

from fastapi.testclient import TestClient

import app as app_module
from llm import (
    LLMProviderJSONDecodeError,
    LLMProviderSchemaValidationError,
    LLMProviderUpstreamError,
    OpenAICompatibleLLMProvider,
)
from schemas import ExtractedFacts, OpenQuestion, PrdQuality


@contextmanager
def temporary_env(**updates: str | None) -> Iterator[None]:
    """中文说明：临时覆盖环境变量，并在退出时恢复原值。"""

    original_values = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def reload_app_module():
    """中文说明：在当前环境变量条件下重新加载 app 模块。"""

    return importlib.reload(app_module)


def build_fake_provider() -> OpenAICompatibleLLMProvider:
    """中文说明：构造用于 monkeypatch 行为测试的 provider 实例。"""

    return OpenAICompatibleLLMProvider(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
    )


def print_result(title: str, payload: object) -> None:
    """中文说明：格式化打印单个验证结果。"""

    print(title)
    print(payload)


def verify_provider_assembly() -> None:
    """中文说明：验证基于环境变量的 provider 装配逻辑。"""

    print("\nASSEMBLY CHECKS")

    with temporary_env(PRD_SKILL_LLM_PROVIDER="stub"):
        provider = app_module.build_llm_provider_from_env()
        print_result("stub provider", type(provider).__name__)

    with temporary_env(
        PRD_SKILL_LLM_PROVIDER="openai_compatible",
        PRD_SKILL_LLM_BASE_URL="https://example.test/v1",
        PRD_SKILL_LLM_API_KEY="secret",
        PRD_SKILL_LLM_MODEL="demo-model",
    ):
        provider = app_module.build_llm_provider_from_env()
        print_result("openai_compatible provider", type(provider).__name__)

    try:
        with temporary_env(
            PRD_SKILL_LLM_PROVIDER="openai_compatible",
            PRD_SKILL_LLM_BASE_URL=None,
            PRD_SKILL_LLM_API_KEY="secret",
            PRD_SKILL_LLM_MODEL="demo-model",
        ):
            app_module.build_llm_provider_from_env()
    except ValueError as exc:
        print_result("missing env validation", str(exc))

    with temporary_env(PRD_SKILL_LLM_PROVIDER="stub"):
        reloaded = reload_app_module()
        print_result("module reload provider", type(reloaded._llm_provider).__name__)


def verify_provider_behaviors() -> None:
    """中文说明：通过 monkeypatch 底层 completion 方法验证 provider 行为。"""

    print("\nPROVIDER BEHAVIOR CHECKS")

    provider = build_fake_provider()

    def completion_success(
        *, prompt: str, temperature: float, response_format: dict[str, str] | None = None
    ) -> dict[str, object]:
        """中文说明：模拟正常 completion 响应。"""

        if "TASK: extract_facts_from_turn" in prompt:
            content = """
{
  "merged_facts": {
    "goal": "提升活动页创建效率",
    "users": ["运营", "市场"],
    "scenarios": ["快速创建活动页"],
    "core_functions": ["模板配置", "页面发布"],
    "conversion_path": ["进入后台", "创建活动", "发布上线"],
    "constraints": ["两周上线"],
    "non_goals": [],
    "data_entities": ["活动：活动ID、活动名称、状态"],
    "success_metrics": ["创建耗时下降50%"],
    "platform": "Web 后台",
    "delivery_scope": ["模板管理", "发布功能"],
    "assumptions": [],
    "open_questions": ["还有哪些风险待确认？"],
    "risks": ["上线时间紧"]
  },
  "open_questions": [
    {
      "key": "assumptions",
      "question": "当前有哪些默认假设成立，后续如果不成立会影响方案？",
      "blocking": false
    }
  ],
  "newly_confirmed_fields": ["goal", "users", "scenarios", "core_functions"],
  "conflicts": [],
  "reasoning_summary": "已完成核心事实提取"
}
""".strip()
        elif "TASK: generate_next_question" in prompt:
            content = """
{
  "primary_question": "当前有哪些默认假设成立，后续如果不成立会影响方案？",
  "secondary_question": null,
  "question_count": 1
}
""".strip()
        else:
            content = "# PRD\n## 1. 背景与目标\n- 提升活动页创建效率\n"
        return {"choices": [{"message": {"content": content}}]}

    provider._create_chat_completion = completion_success  # type: ignore[method-assign]

    extraction = provider.extract_facts_from_turn(
        existing_facts=ExtractedFacts(),
        input_text="想做一个帮助运营快速创建活动页的工具",
        project_context="已有 Web 后台",
    )
    print_result(
        "extract_facts_from_turn",
        {
            "goal": extraction.merged_facts.goal,
            "open_questions": [question.question for question in extraction.open_questions],
        },
    )

    next_question = provider.generate_next_question(
        facts=extraction.merged_facts,
        open_questions=extraction.open_questions,
        project_context="已有 Web 后台",
    )
    print_result("generate_next_question", next_question.model_dump())

    prd_markdown = provider.draft_prd_from_facts(
        facts=extraction.merged_facts,
        project_context="已有 Web 后台",
        quality=PrdQuality.DRAFT,
    )
    print_result("draft_prd_from_facts", prd_markdown.splitlines()[:3])

    fallback_provider = build_fake_provider()

    def completion_with_fallback(
        *, prompt: str, temperature: float, response_format: dict[str, str] | None = None
    ) -> dict[str, object]:
        """中文说明：模拟 response_format 不支持时的回退行为。"""

        if response_format is not None:
            raise LLMProviderUpstreamError("response_format not supported")
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "说明文本\n"
                            '{\n'
                            '  "primary_question": "请补充成功指标。",\n'
                            '  "secondary_question": null,\n'
                            '  "question_count": 1\n'
                            '}'
                        )
                    }
                }
            ]
        }

    fallback_provider._create_chat_completion = completion_with_fallback  # type: ignore[method-assign]
    fallback_question = fallback_provider.generate_next_question(
        facts=ExtractedFacts(goal="提升效率"),
        open_questions=[OpenQuestion(key="success_metrics", question="请补充成功指标。", blocking=True)],
        project_context=None,
    )
    print_result("response_format fallback", fallback_question.model_dump())

    invalid_json_provider = build_fake_provider()

    def completion_invalid_json(
        *, prompt: str, temperature: float, response_format: dict[str, str] | None = None
    ) -> dict[str, object]:
        """中文说明：模拟 completion 返回非法 JSON 文本。"""

        return {"choices": [{"message": {"content": "not-json-at-all"}}]}

    invalid_json_provider._create_chat_completion = completion_invalid_json  # type: ignore[method-assign]
    try:
        invalid_json_provider.generate_next_question(
            facts=ExtractedFacts(goal="提升效率"),
            open_questions=[OpenQuestion(key="success_metrics", question="请补充成功指标。", blocking=True)],
            project_context=None,
        )
    except LLMProviderJSONDecodeError as exc:
        print_result("invalid json", str(exc))

    invalid_schema_provider = build_fake_provider()

    def completion_invalid_schema(
        *, prompt: str, temperature: float, response_format: dict[str, str] | None = None
    ) -> dict[str, object]:
        """中文说明：模拟 completion 返回结构不符合 schema 的 JSON。"""

        return {
            "choices": [
                {
                    "message": {
                        "content": '{"primary_question": "请补充成功指标。", "question_count": 2}'
                    }
                }
            ]
        }

    invalid_schema_provider._create_chat_completion = completion_invalid_schema  # type: ignore[method-assign]
    try:
        invalid_schema_provider.generate_next_question(
            facts=ExtractedFacts(goal="提升效率"),
            open_questions=[OpenQuestion(key="success_metrics", question="请补充成功指标。", blocking=True)],
            project_context=None,
        )
    except LLMProviderSchemaValidationError as exc:
        print_result("invalid schema", str(exc))


def verify_api_flow_with_fake_provider() -> None:
    """中文说明：验证接口链路可通过真实 provider 类路径完成交互。"""

    print("\nAPI FLOW CHECKS")

    fake_provider = build_fake_provider()

    def completion_success(
        *, prompt: str, temperature: float, response_format: dict[str, str] | None = None
    ) -> dict[str, object]:
        """中文说明：为 API 冒烟测试提供稳定的 completion 响应。"""

        if "TASK: extract_facts_from_turn" in prompt:
            if "INPUT_TEXT:\n补充成功指标" in prompt:
                content = """
{
  "merged_facts": {
    "goal": "提升活动页创建效率",
    "users": ["运营"],
    "scenarios": ["快速创建活动页"],
    "core_functions": ["模板配置", "页面发布"],
    "conversion_path": ["进入后台", "创建活动", "发布上线"],
    "constraints": ["两周上线"],
    "non_goals": [],
    "data_entities": ["活动：活动ID、活动名称、状态"],
    "success_metrics": ["创建耗时下降50%"],
    "platform": "Web 后台",
    "delivery_scope": ["模板管理", "发布功能"],
    "assumptions": [],
    "open_questions": [],
    "risks": []
  },
  "open_questions": [],
  "newly_confirmed_fields": ["success_metrics"],
  "conflicts": [],
  "reasoning_summary": "已补充成功指标"
}
""".strip()
            else:
                content = """
{
  "merged_facts": {
    "goal": "提升活动页创建效率",
    "users": ["运营"],
    "scenarios": ["快速创建活动页"],
    "core_functions": ["模板配置", "页面发布"],
    "conversion_path": ["进入后台", "创建活动", "发布上线"],
    "constraints": ["两周上线"],
    "non_goals": [],
    "data_entities": ["活动：活动ID、活动名称、状态"],
    "success_metrics": [],
    "platform": "Web 后台",
    "delivery_scope": ["模板管理", "发布功能"],
    "assumptions": [],
    "open_questions": ["请补充成功指标。"],
    "risks": []
  },
  "open_questions": [
    {
      "key": "success_metrics",
      "question": "请补充成功指标。",
      "blocking": true
    }
  ],
  "newly_confirmed_fields": ["goal", "users", "scenarios", "core_functions"],
  "conflicts": [],
  "reasoning_summary": "待补充成功指标"
}
""".strip()
        elif "TASK: generate_next_question" in prompt:
            content = """
{
  "primary_question": "请补充成功指标。",
  "secondary_question": null,
  "question_count": 1
}
""".strip()
        else:
            content = "# PRD\n## 1. 背景与目标\n- 提升活动页创建效率\n## 2. 用户与场景\n- 运营\n"
        return {"choices": [{"message": {"content": content}}]}

    fake_provider._create_chat_completion = completion_success  # type: ignore[method-assign]
    app_module._llm_provider = fake_provider
    app_module._service._llm_provider = fake_provider
    client = TestClient(app_module.app)

    start_resp = client.post(
        "/session/start",
        json={"mode": "interactive", "input_text": "想做一个帮助运营快速创建活动页的工具"},
    )
    start_body = start_resp.json()
    print_result(
        "/session/start",
        {
            "status_code": start_resp.status_code,
            "provider": type(app_module._llm_provider).__name__,
            "open_questions": start_body["open_questions"],
        },
    )

    continue_resp = client.post(
        "/session/continue",
        json={"session_id": start_body["session_id"], "input_text": "补充成功指标"},
    )
    continue_body = continue_resp.json()
    print_result(
        "/session/continue",
        {
            "status_code": continue_resp.status_code,
            "open_questions": continue_body["open_questions"],
        },
    )

    prd_resp = client.post(
        "/prd/generate",
        json={"session_id": start_body["session_id"], "quality": "draft"},
    )
    prd_body = prd_resp.json()
    print_result(
        "/prd/generate draft",
        {
            "status_code": prd_resp.status_code,
            "quality": prd_body["quality"],
            "markdown_head": prd_body["markdown"].splitlines()[:3],
        },
    )

    error_provider = build_fake_provider()

    def completion_invalid_json(
        *, prompt: str, temperature: float, response_format: dict[str, str] | None = None
    ) -> dict[str, object]:
        """中文说明：模拟 API 链路中的非法 JSON 异常。"""

        return {"choices": [{"message": {"content": "not-json"}}]}

    error_provider._create_chat_completion = completion_invalid_json  # type: ignore[method-assign]
    app_module._llm_provider = error_provider
    app_module._service._llm_provider = error_provider

    error_client = TestClient(app_module.app)
    error_resp = error_client.post(
        "/session/start",
        json={"mode": "interactive", "input_text": "想做一个帮助运营快速创建活动页的工具"},
    )
    print_result(
        "/session/start invalid json",
        {
            "status_code": error_resp.status_code,
            "body": error_resp.json(),
        },
    )


def main() -> None:
    """中文说明：运行本地装配层、provider 行为层与 API 链路冒烟验证。"""

    verify_provider_assembly()
    verify_provider_behaviors()
    verify_api_flow_with_fake_provider()


if __name__ == "__main__":
    main()
