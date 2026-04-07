"""prd_skill 的本地冒烟测试脚本。"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from fastapi.testclient import TestClient

import app as app_module
from llm import (
    LLMProviderJSONDecodeError,
    OpenAICompatibleLLMProvider,
    StubLLMProvider,
)
from schemas import ExtractedFacts, OpenQuestion, PrdQuality
from settings import (
    LLMProviderSettings,
    LLMProviderSettingsError,
    load_llm_provider_settings,
)


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


def print_result(title: str, payload: object) -> None:
    """中文说明：格式化打印单个验证结果。"""

    print(title)
    print(payload)


def build_openai_settings(
    *,
    response_format_enabled: bool = True,
    temperature_json: float = 0.1,
    temperature_text: float = 0.3,
    timeout_seconds: float = 30.0,
) -> LLMProviderSettings:
    """中文说明：构造测试用的 openai-compatible provider 配置。"""

    return LLMProviderSettings(
        provider="openai_compatible",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        temperature_json=temperature_json,
        temperature_text=temperature_text,
        timeout_seconds=timeout_seconds,
        api_style="openai_compatible",
        response_format_enabled=response_format_enabled,
    )


def build_fake_provider(
    *,
    response_format_enabled: bool = True,
    temperature_json: float = 0.1,
    temperature_text: float = 0.3,
    timeout_seconds: float = 30.0,
) -> OpenAICompatibleLLMProvider:
    """中文说明：使用最新版 settings 构造 provider 测试替身。"""

    return OpenAICompatibleLLMProvider(
        settings=LLMProviderSettings(
            provider="openai_compatible",
            base_url="https://example.test/v1",
            api_key="test-key",
            model="test-model",
            temperature_json=temperature_json,
            temperature_text=temperature_text,
            timeout_seconds=timeout_seconds,
            api_style="openai_compatible",
            response_format_enabled=response_format_enabled,
        )
    )


def _expect_settings_error(env: dict[str, str], label: str) -> None:
    """中文说明：断言加载配置时抛出 settings 异常。"""

    try:
        load_llm_provider_settings(env)
    except LLMProviderSettingsError as exc:
        print_result(label, str(exc))
        return
    raise AssertionError(f"{label} should raise LLMProviderSettingsError")


def _fake_llm_response_for_prompt(prompt: str) -> str:
    """中文说明：根据 prompt 返回稳定的测试响应文本。"""

    if "TASK: extract_facts_from_turn" in prompt:
        if "INPUT_TEXT:\n补充成功指标" in prompt:
            return """
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
        return """
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
    if "TASK: generate_next_question" in prompt:
        return """
{
  "primary_question": "请补充成功指标。",
  "secondary_question": null,
  "question_count": 1
}
""".strip()
    return "# PRD\n## 1. 背景与目标\n- 提升活动页创建效率\n## 2. 用户与场景\n- 运营\n"


def verify_settings_loading() -> None:
    """中文说明：验证 settings 层的默认值、正常加载与非法配置报错。"""

    print("\nSETTINGS CHECKS")

    default_settings = load_llm_provider_settings({})
    assert default_settings.provider == "stub"
    assert default_settings.api_style == "openai_compatible"
    assert default_settings.temperature_json == 0.1
    assert default_settings.temperature_text == 0.3
    assert default_settings.timeout_seconds == 30.0
    assert default_settings.response_format_enabled is True
    print_result("default settings", default_settings)

    configured_settings = load_llm_provider_settings(
        {
            "PRD_SKILL_LLM_PROVIDER": "openai_compatible",
            "PRD_SKILL_LLM_BASE_URL": "https://example.test/v1",
            "PRD_SKILL_LLM_API_KEY": "secret",
            "PRD_SKILL_LLM_MODEL": "demo-model",
            "PRD_SKILL_LLM_TEMPERATURE_JSON": "0.55",
            "PRD_SKILL_LLM_TEMPERATURE_TEXT": "0.66",
            "PRD_SKILL_LLM_TIMEOUT_SECONDS": "12.5",
            "PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED": "false",
            "PRD_SKILL_LLM_API_STYLE": "openai_compatible",
        }
    )
    assert configured_settings.provider == "openai_compatible"
    assert configured_settings.base_url == "https://example.test/v1"
    assert configured_settings.api_key == "secret"
    assert configured_settings.model == "demo-model"
    assert configured_settings.temperature_json == 0.55
    assert configured_settings.temperature_text == 0.66
    assert configured_settings.timeout_seconds == 12.5
    assert configured_settings.response_format_enabled is False
    print_result("configured settings", configured_settings)

    _expect_settings_error(
        {
            "PRD_SKILL_LLM_PROVIDER": "openai_compatible",
            "PRD_SKILL_LLM_BASE_URL": "https://example.test/v1",
            "PRD_SKILL_LLM_API_KEY": "secret",
            "PRD_SKILL_LLM_MODEL": "demo-model",
            "PRD_SKILL_LLM_TIMEOUT_SECONDS": "abc",
        },
        "invalid timeout",
    )
    _expect_settings_error(
        {
            "PRD_SKILL_LLM_PROVIDER": "openai_compatible",
            "PRD_SKILL_LLM_BASE_URL": "https://example.test/v1",
            "PRD_SKILL_LLM_API_KEY": "secret",
            "PRD_SKILL_LLM_MODEL": "demo-model",
            "PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED": "maybe",
        },
        "invalid response_format_enabled",
    )
    _expect_settings_error(
        {
            "PRD_SKILL_LLM_PROVIDER": "openai_compatible",
            "PRD_SKILL_LLM_API_KEY": "secret",
            "PRD_SKILL_LLM_MODEL": "demo-model",
        },
        "missing required openai fields",
    )


def verify_provider_assembly() -> None:
    """中文说明：验证 app 层 provider 装配逻辑。"""

    print("\nASSEMBLY CHECKS")

    stub_provider = app_module.build_llm_provider_from_settings(
        load_llm_provider_settings({})
    )
    assert isinstance(stub_provider, StubLLMProvider)
    print_result("stub provider", type(stub_provider).__name__)

    openai_provider = app_module.build_llm_provider_from_settings(
        build_openai_settings()
    )
    assert isinstance(openai_provider, OpenAICompatibleLLMProvider)
    print_result("openai_compatible provider", type(openai_provider).__name__)

    with temporary_env(PRD_SKILL_LLM_PROVIDER="stub"):
        env_provider = app_module.build_llm_provider_from_env()
        assert isinstance(env_provider, StubLLMProvider)
        print_result("env stub provider", type(env_provider).__name__)

    with temporary_env(
        PRD_SKILL_LLM_PROVIDER="openai_compatible",
        PRD_SKILL_LLM_BASE_URL="https://example.test/v1",
        PRD_SKILL_LLM_API_KEY="secret",
        PRD_SKILL_LLM_MODEL="demo-model",
    ):
        env_provider = app_module.build_llm_provider_from_env()
        assert isinstance(env_provider, OpenAICompatibleLLMProvider)
        print_result("env openai provider", type(env_provider).__name__)


def verify_provider_behaviors() -> None:
    """中文说明：通过 monkeypatch `_send_chat_completion_request` 验证 provider 行为。"""

    print("\nPROVIDER BEHAVIOR CHECKS")

    provider = build_fake_provider(
        response_format_enabled=True,
        temperature_json=0.45,
        temperature_text=0.67,
        timeout_seconds=12.5,
    )
    captured_payloads: list[dict[str, Any]] = []

    def send_success(payload: dict[str, Any]) -> dict[str, object]:
        """中文说明：记录 payload 并返回稳定的 completion 响应。"""

        captured_payloads.append(payload)
        prompt = str(payload["messages"][0]["content"])
        return {"choices": [{"message": {"content": _fake_llm_response_for_prompt(prompt)}}]}

    provider._send_chat_completion_request = send_success  # type: ignore[method-assign]

    request_url = provider._build_request_url()
    assert request_url.endswith("/chat/completions")
    assert provider._settings.timeout_seconds == 12.5
    print_result("request url", request_url)

    extraction = provider.extract_facts_from_turn(
        existing_facts=ExtractedFacts(),
        input_text="想做一个帮助运营快速创建活动页的工具",
        project_context="已有 Web 后台",
    )
    json_payload = captured_payloads[-1]
    assert json_payload["temperature"] == 0.45
    assert json_payload["response_format"] == {"type": "json_object"}
    print_result(
        "extract_facts_from_turn",
        {
            "goal": extraction.merged_facts.goal,
            "temperature": json_payload["temperature"],
            "response_format": json_payload.get("response_format"),
            "timeout_seconds": provider._settings.timeout_seconds,
        },
    )

    next_question = provider.generate_next_question(
        facts=extraction.merged_facts,
        open_questions=extraction.open_questions,
        project_context="已有 Web 后台",
    )
    next_question_payload = captured_payloads[-1]
    assert next_question_payload["temperature"] == 0.45
    assert next_question_payload["response_format"] == {"type": "json_object"}
    print_result("generate_next_question", next_question.model_dump())

    prd_markdown = provider.draft_prd_from_facts(
        facts=extraction.merged_facts,
        project_context="已有 Web 后台",
        quality=PrdQuality.DRAFT,
    )
    text_payload = captured_payloads[-1]
    assert text_payload["temperature"] == 0.67
    assert "response_format" not in text_payload
    print_result(
        "draft_prd_from_facts",
        {
            "markdown_head": prd_markdown.splitlines()[:3],
            "temperature": text_payload["temperature"],
        },
    )

    disabled_provider = build_fake_provider(response_format_enabled=False)
    disabled_payloads: list[dict[str, Any]] = []

    def send_without_response_format(payload: dict[str, Any]) -> dict[str, object]:
        """中文说明：关闭 response_format 后仍返回可提取 JSON 的文本。"""

        disabled_payloads.append(payload)
        prompt = str(payload["messages"][0]["content"])
        if "TASK: generate_next_question" in prompt:
            content = (
                "说明文本\n"
                '{\n'
                '  "primary_question": "请补充成功指标。",\n'
                '  "secondary_question": null,\n'
                '  "question_count": 1\n'
                '}'
            )
        else:
            content = _fake_llm_response_for_prompt(prompt)
        return {"choices": [{"message": {"content": content}}]}

    disabled_provider._send_chat_completion_request = send_without_response_format  # type: ignore[method-assign]
    disabled_question = disabled_provider.generate_next_question(
        facts=ExtractedFacts(goal="提升效率"),
        open_questions=[
            OpenQuestion(
                key="success_metrics",
                question="请补充成功指标。",
                blocking=True,
            )
        ],
        project_context=None,
    )
    disabled_payload = disabled_payloads[-1]
    assert disabled_payload["temperature"] == 0.1
    assert "response_format" not in disabled_payload
    assert disabled_question.primary_question == "请补充成功指标。"
    print_result("response_format disabled", disabled_question.model_dump())

    invalid_json_provider = build_fake_provider(response_format_enabled=False)

    def send_invalid_json(payload: dict[str, Any]) -> dict[str, object]:
        """中文说明：模拟 completion 返回无法提取 JSON 的文本。"""

        return {"choices": [{"message": {"content": "not-json-at-all"}}]}

    invalid_json_provider._send_chat_completion_request = send_invalid_json  # type: ignore[method-assign]
    try:
        invalid_json_provider.generate_next_question(
            facts=ExtractedFacts(goal="提升效率"),
            open_questions=[
                OpenQuestion(
                    key="success_metrics",
                    question="请补充成功指标。",
                    blocking=True,
                )
            ],
            project_context=None,
        )
    except LLMProviderJSONDecodeError as exc:
        print_result("invalid json", str(exc))
    else:
        raise AssertionError("invalid json should raise LLMProviderJSONDecodeError")


def verify_api_flow_with_fake_provider() -> None:
    """中文说明：验证 API 链路可通过真实 provider 类路径完成交互。"""

    print("\nAPI FLOW CHECKS")

    fake_provider = build_fake_provider(response_format_enabled=True)

    def send_success(payload: dict[str, Any]) -> dict[str, object]:
        """中文说明：为 API 冒烟测试提供稳定的 completion 响应。"""

        prompt = str(payload["messages"][0]["content"])
        return {"choices": [{"message": {"content": _fake_llm_response_for_prompt(prompt)}}]}

    fake_provider._send_chat_completion_request = send_success  # type: ignore[method-assign]
    app_module._llm_provider = fake_provider
    app_module._service._llm_provider = fake_provider
    client = TestClient(app_module.app)

    start_resp = client.post(
        "/session/start",
        json={"mode": "interactive", "input_text": "想做一个帮助运营快速创建活动页的工具"},
    )
    start_body = start_resp.json()
    assert start_resp.status_code == 200
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
    assert continue_resp.status_code == 200
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
    assert prd_resp.status_code == 200
    print_result(
        "/prd/generate",
        {
            "status_code": prd_resp.status_code,
            "quality": prd_body["quality"],
            "markdown_head": prd_body["markdown"].splitlines()[:3],
        },
    )

    error_provider = build_fake_provider(response_format_enabled=False)

    def send_invalid_json(payload: dict[str, Any]) -> dict[str, object]:
        """中文说明：模拟 API 链路中的非法 JSON 异常。"""

        return {"choices": [{"message": {"content": "not-json"}}]}

    error_provider._send_chat_completion_request = send_invalid_json  # type: ignore[method-assign]
    app_module._llm_provider = error_provider
    app_module._service._llm_provider = error_provider
    error_client = TestClient(app_module.app)

    error_resp = error_client.post(
        "/session/start",
        json={"mode": "interactive", "input_text": "想做一个帮助运营快速创建活动页的工具"},
    )
    assert error_resp.status_code == 502
    print_result(
        "/session/start invalid json",
        {
            "status_code": error_resp.status_code,
            "body": error_resp.json(),
        },
    )


def main() -> None:
    """中文说明：运行配置层、装配层、provider 行为层与 API 链路冒烟验证。"""

    verify_settings_loading()
    verify_provider_assembly()
    verify_provider_behaviors()
    verify_api_flow_with_fake_provider()


if __name__ == "__main__":
    main()
