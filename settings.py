"""prd_skill 的 LLM provider 配置加载模块。"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Mapping, Optional


class LLMProviderSettingsError(ValueError):
    """中文说明：LLM provider 配置非法时抛出的统一异常。"""


@dataclass(frozen=True)
class LLMProviderSettings:
    """中文说明：LLM provider 的不可变运行配置。"""

    provider: str
    base_url: Optional[str]
    api_key: Optional[str]
    model: Optional[str]
    temperature_json: float
    temperature_text: float
    timeout_seconds: float
    api_style: str
    response_format_enabled: bool


def load_llm_provider_settings_from_env() -> LLMProviderSettings:
    """中文说明：从当前进程环境变量中加载 LLM provider 配置。"""

    return load_llm_provider_settings(os.environ)


def load_llm_provider_settings(env: Mapping[str, str]) -> LLMProviderSettings:
    """中文说明：从给定映射中加载、补全并校验后返回 LLM provider 配置。"""

    loaded_settings = LLMProviderSettings(
        provider=_read_string(env, "PRD_SKILL_LLM_PROVIDER", default="stub"),
        base_url=_read_optional_string(env, "PRD_SKILL_LLM_BASE_URL"),
        api_key=_read_optional_string(env, "PRD_SKILL_LLM_API_KEY"),
        model=_read_optional_string(env, "PRD_SKILL_LLM_MODEL"),
        temperature_json=_read_float(
            env,
            "PRD_SKILL_LLM_TEMPERATURE_JSON",
            default=0.1,
        ),
        temperature_text=_read_float(
            env,
            "PRD_SKILL_LLM_TEMPERATURE_TEXT",
            default=0.3,
        ),
        timeout_seconds=_read_float(
            env,
            "PRD_SKILL_LLM_TIMEOUT_SECONDS",
            default=30.0,
        ),
        api_style=_read_string(
            env,
            "PRD_SKILL_LLM_API_STYLE",
            default="openai_compatible",
        ),
        response_format_enabled=_read_bool(
            env,
            "PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED",
            default=True,
        ),
    )
    resolved_settings = resolve_llm_provider_settings(loaded_settings)
    validate_llm_provider_settings(resolved_settings)
    return resolved_settings


def resolve_llm_provider_settings(settings: LLMProviderSettings) -> LLMProviderSettings:
    """中文说明：对已加载配置做语义补全与标准化。"""

    return replace(
        settings,
        provider=settings.provider.strip().lower(),
        api_style=settings.api_style.strip().lower(),
        base_url=settings.base_url.strip() if settings.base_url is not None else None,
        api_key=settings.api_key.strip() if settings.api_key is not None else None,
        model=settings.model.strip() if settings.model is not None else None,
    )


def validate_llm_provider_settings(settings: LLMProviderSettings) -> None:
    """中文说明：校验 provider 配置是否合法，并在非法时抛出清晰错误。"""

    _validate_provider(settings.provider)
    _validate_api_style(settings.api_style)
    _validate_numeric_fields(settings)
    if settings.provider == "openai_compatible":
        _validate_required_openai_fields(
            {
                "PRD_SKILL_LLM_BASE_URL": settings.base_url,
                "PRD_SKILL_LLM_API_KEY": settings.api_key,
                "PRD_SKILL_LLM_MODEL": settings.model,
            }
        )


def _read_string(env: Mapping[str, str], key: str, *, default: str) -> str:
    """中文说明：读取字符串配置；为空时回退到默认值。"""

    raw_value = env.get(key)
    if raw_value is None:
        return default
    cleaned = raw_value.strip()
    return cleaned or default


def _read_optional_string(env: Mapping[str, str], key: str) -> Optional[str]:
    """中文说明：读取可选字符串配置；空串按未配置处理。"""

    raw_value = env.get(key)
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    return cleaned or None


def _read_float(env: Mapping[str, str], key: str, *, default: float) -> float:
    """中文说明：读取浮点配置，并在类型非法时给出清晰错误。"""

    raw_value = env.get(key)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return float(raw_value.strip())
    except ValueError as exc:
        raise LLMProviderSettingsError(
            f"{key} 必须是合法浮点数，当前值为: {raw_value}"
        ) from exc


def _read_bool(env: Mapping[str, str], key: str, *, default: bool) -> bool:
    """中文说明：读取布尔配置，并严格兼容常见 true/false 表达。"""

    raw_value = env.get(key)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    truthy_values = {"true", "1", "yes", "on"}
    falsy_values = {"false", "0", "no", "off"}
    if normalized in truthy_values:
        return True
    if normalized in falsy_values:
        return False
    raise LLMProviderSettingsError(
        f"{key} 必须是 true/false、1/0、yes/no 或 on/off，当前值为: {raw_value}"
    )


def _validate_provider(provider: str) -> None:
    """中文说明：校验 provider 类型是否在当前支持范围内。"""

    allowed_values = {"stub", "openai_compatible"}
    if provider not in allowed_values:
        raise LLMProviderSettingsError(
            "PRD_SKILL_LLM_PROVIDER 非法，当前仅支持: stub, openai_compatible"
        )


def _validate_api_style(api_style: str) -> None:
    """中文说明：校验 API 风格配置是否在当前支持范围内。"""

    if api_style != "openai_compatible":
        raise LLMProviderSettingsError(
            "PRD_SKILL_LLM_API_STYLE 非法，当前仅支持: openai_compatible"
        )


def _validate_numeric_fields(settings: LLMProviderSettings) -> None:
    """中文说明：校验超时与 temperature 数值范围是否合法。"""

    if settings.timeout_seconds <= 0:
        raise LLMProviderSettingsError(
            "PRD_SKILL_LLM_TIMEOUT_SECONDS 必须大于 0。"
        )
    if settings.temperature_json < 0:
        raise LLMProviderSettingsError(
            "PRD_SKILL_LLM_TEMPERATURE_JSON 必须大于等于 0。"
        )
    if settings.temperature_text < 0:
        raise LLMProviderSettingsError(
            "PRD_SKILL_LLM_TEMPERATURE_TEXT 必须大于等于 0。"
        )


def _validate_required_openai_fields(fields: Mapping[str, Optional[str]]) -> None:
    """中文说明：校验 openai-compatible 模式下的必填配置。"""

    missing_fields = [key for key, value in fields.items() if not value]
    if missing_fields:
        raise LLMProviderSettingsError(
            "OpenAI-compatible provider 缺少必要环境变量: "
            + ", ".join(missing_fields)
        )


__all__ = [
    "LLMProviderSettings",
    "LLMProviderSettingsError",
    "load_llm_provider_settings",
    "load_llm_provider_settings_from_env",
    "resolve_llm_provider_settings",
    "validate_llm_provider_settings",
]
