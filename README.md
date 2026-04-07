# prd_skill

`prd_skill` 是一个基于 FastAPI 的 PRD 生成服务，支持多轮 interactive 访谈、reverse PRD 生成，以及基于 PRD 的任务拆解。

## LLM Provider 配置

当前服务支持两种 provider 模式：

- `stub`：本地规则实现，适合开发联调与无外部模型场景
- `openai_compatible`：通过 OpenAI-compatible `/chat/completions` 接口调用真实 LLM

### 1. 使用 stub 模式

只需要配置：

```bash
export PRD_SKILL_LLM_PROVIDER=stub
```

stub 模式不会读取 `base_url`、`api_key`、`model`，适合本地开发和基本功能验证。

### 2. 切换到 openai_compatible 模式

至少需要配置：

```bash
export PRD_SKILL_LLM_PROVIDER=openai_compatible
export PRD_SKILL_LLM_BASE_URL=https://your-provider.example/v1
export PRD_SKILL_LLM_API_KEY=your_api_key
export PRD_SKILL_LLM_MODEL=your_model_name
```

### 3. 支持的环境变量

- `PRD_SKILL_LLM_PROVIDER`
  - 可选值：`stub`、`openai_compatible`
  - 默认值：`stub`
- `PRD_SKILL_LLM_BASE_URL`
  - `openai_compatible` 模式必填
  - 用于指定兼容接口的服务根地址
- `PRD_SKILL_LLM_API_KEY`
  - `openai_compatible` 模式必填
- `PRD_SKILL_LLM_MODEL`
  - `openai_compatible` 模式必填
- `PRD_SKILL_LLM_TEMPERATURE_JSON`
  - 用于 facts 抽取与下一问生成等结构化任务
  - 默认值：`0.1`
- `PRD_SKILL_LLM_TEMPERATURE_TEXT`
  - 用于 PRD markdown 生成等文本任务
  - 默认值：`0.3`
- `PRD_SKILL_LLM_TIMEOUT_SECONDS`
  - 请求超时时间，单位秒
  - 默认值：`30`
- `PRD_SKILL_LLM_API_STYLE`
  - 当前仅支持：`openai_compatible`
  - 默认值：`openai_compatible`
- `PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED`
  - 是否在结构化任务请求中启用 `response_format={"type":"json_object"}`
  - 默认值：`true`
  - 支持值：`true/false`、`1/0`、`yes/no`、`on/off`

### 4. `.env.example` 示例

仓库已提供 [.env.example](/Users/mason/project/prd_skill/.env.example)，可以直接复制后修改。示例中同时给出了 `stub` 和 `openai_compatible` 的填写方式。

### 5. 如何修改 base_url / model / timeout / temperature

通过环境变量直接控制：

```bash
export PRD_SKILL_LLM_BASE_URL=https://your-provider.example/v1
export PRD_SKILL_LLM_MODEL=your_model_name
export PRD_SKILL_LLM_TIMEOUT_SECONDS=45
export PRD_SKILL_LLM_TEMPERATURE_JSON=0.05
export PRD_SKILL_LLM_TEMPERATURE_TEXT=0.4
```

### 6. 如何关闭 response_format

如果你的 OpenAI-compatible 服务不支持 `response_format`，可以关闭：

```bash
export PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED=false
```

关闭后会保持当前语义不变：

- 结构化任务仍优先要求模型输出 JSON
- 请求体中不再传 `response_format`
- provider 仍会从普通文本中提取 JSON 对象并继续做 schema 校验

### 7. 当前能力边界与限制

当前真实 provider 的能力边界如下：

- 当前仅支持 OpenAI-compatible `/chat/completions`
- 不支持 Responses API
- 不支持流式输出
- 不支持多模型路由
- `api_style` 当前仅支持 `openai_compatible`
- `service.py` 不感知 HTTP、JSON 提取或厂商协议细节
- interactive v2 的状态机、facts schema、reverse 范围和 tasks/generate 能力不会因为 provider 配置而改变
