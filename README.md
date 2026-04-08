# prd_skill

`prd_skill` 是一个基于 FastAPI 的 PRD 服务，目标是提供一条可运行、可扩展的需求收敛与文档生成链路。

当前已具备的核心能力包括：

- 会话管理
- interactive 模式下的多轮需求收敛
- reverse 模式下的单次 PRD 生成
- PRD markdown 输出
- 基于 PRD markdown 的任务拆解


## 1. 文档索引

- `README.md`：项目入口与使用方式
- `AGENTS.md`：AI 和开发者的工作规则
- `ARCHITECTURE.md`：系统分层与主链路说明
- `PRODUCT_STATE.md`：当前项目状态
- `DECISIONS.md`：关键决策记录
- `TASKS.md`：当前任务列表


## 2. 当前技术栈

- Python 3.11+
- FastAPI
- Pydantic v2
- `httpx`
- `uvicorn`
- `fastapi.testclient`


## 3. 当前目录概览

当前仓库采用根目录平铺模块组织方式，核心文件包括：

- `app.py`：FastAPI 入口与路由注册
- `service.py`：核心业务编排
- `schemas.py`：请求 / 响应模型与枚举
- `prompts.py`：prompt 模板与构造
- `llm.py`：LLM 抽象与 provider 实现
- `session_store.py`：session 存储抽象
- `settings.py`：配置读取与校验
- `smoke_test.py`：主冒烟测试入口

## 4. 快速开始

### 4.1 安装依赖

当前仓库**没有提交 `requirements.txt` 或 `pyproject.toml`**，因此新接手时需要先手动安装最小依赖。

建议使用 Python 3.11+：

```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx pydantic
```

如果你的环境里还没有 FastAPI 的测试依赖，可一并安装：

```bash
pip install "fastapi[standard]"
```

### 4.2 配置环境变量

仓库提供了 `.env.example`，可先复制为本地环境配置：

```bash
cp .env.example .env
```

关键环境变量如下：

```bash
PRD_SKILL_LLM_PROVIDER=stub
PRD_SKILL_LLM_API_STYLE=openai_compatible
PRD_SKILL_LLM_BASE_URL=https://your-provider.example/v1
PRD_SKILL_LLM_API_KEY=your_api_key_here
PRD_SKILL_LLM_MODEL=your_model_name_here
PRD_SKILL_LLM_TEMPERATURE_JSON=0.1
PRD_SKILL_LLM_TEMPERATURE_TEXT=0.3
PRD_SKILL_LLM_TIMEOUT_SECONDS=30
PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED=true
```

重点说明：

- `PRD_SKILL_LLM_PROVIDER`
  - 可选值：`stub`、`openai_compatible`
  - 默认值：`stub`
- `PRD_SKILL_LLM_BASE_URL`
  - `openai_compatible` 模式必填
- `PRD_SKILL_LLM_API_KEY`
  - `openai_compatible` 模式必填
- `PRD_SKILL_LLM_MODEL`
  - `openai_compatible` 模式必填
- `PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED`
  - 是否在结构化任务里启用 `response_format={"type":"json_object"}`
  - 如果第三方兼容接口不支持该参数，可以关闭
- `PRD_SKILL_LLM_TEMPERATURE_JSON`
  - 用于 facts 抽取、下一问生成等结构化任务
- `PRD_SKILL_LLM_TEMPERATURE_TEXT`
  - 用于 PRD markdown 生成

本地联调推荐两种方式：

#### 方式一：使用 stub

```bash
export PRD_SKILL_LLM_PROVIDER=stub
```

适合：

- 本地开发
- 不依赖外部模型
- 先验证接口和状态机

#### 方式二：使用 openai-compatible provider

```bash
export PRD_SKILL_LLM_PROVIDER=openai_compatible
export PRD_SKILL_LLM_BASE_URL=https://your-provider.example/v1
export PRD_SKILL_LLM_API_KEY=your_api_key
export PRD_SKILL_LLM_MODEL=your_model_name
export PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED=true
```

如果上游不支持 `response_format`：

```bash
export PRD_SKILL_LLM_RESPONSE_FORMAT_ENABLED=false
```

### 4.3 启动服务

```bash
uvicorn app:app --reload
```

默认启动后可访问：

- `http://127.0.0.1:8000/health`

## 5 调用示例

### 5.1 健康检查

```bash
curl http://127.0.0.1:8000/health
```

### 5.2 启动 interactive 会话

```bash
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "interactive",
    "input_text": "想做一个帮助运营快速创建活动页的工具",
    "project_context": "已有 Web 后台"
  }'
```

### 5.3 继续会话

```bash
curl -X POST http://127.0.0.1:8000/session/continue \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "your-session-id",
    "input_text": "成功指标是活动页创建耗时下降 50%"
  }'
```

### 5.4 基于 session 生成 PRD

```bash
curl -X POST http://127.0.0.1:8000/prd/generate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "your-session-id",
    "quality": "draft"
  }'
```

### 5.5 one-shot 生成 PRD

```bash
curl -X POST http://127.0.0.1:8000/prd/generate \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "interactive",
    "input_text": "做一个面向运营的活动页创建工具，支持模板配置、页面发布、查看转化效果",
    "project_context": "已有 Web 后台",
    "quality": "final"
  }'
```

### 5.6 基于 PRD 生成任务

```bash
curl -X POST http://127.0.0.1:8000/tasks/generate \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "prd_skill",
    "prd_markdown": "# PRD\n## 1. 背景与目标\n..."
  }'
```

## 6. 测试与验证

### `python smoke_test.py` 的作用

当前仓库最重要的本地验证入口是：

```bash
python smoke_test.py
```

它主要验证以下内容：

- settings 加载与默认值
- 非法环境变量的报错行为
- `stub` 与 `openai_compatible` provider 装配逻辑
- `response_format` 开关行为
- JSON fallback 提取逻辑
- provider 返回非法 JSON 时的错误映射
- `/session/start`
- `/session/continue`
- `/prd/generate`

需要注意的是：

- 这个脚本使用了 `OpenAICompatibleLLMProvider` 的真实代码路径
- 但通过 monkeypatch 替代了实际 HTTP 请求
- 所以它能证明：
  - provider 集成方式正确
  - API 主链路可跑通
  - 结构化输出兼容逻辑有效
- 但它**不等于真实第三方模型效果验证**

## 7. 当前工程现实

在开始修改前，建议先了解以下现状：

- 仓库目前较小，核心代码集中在根目录
- 当前没有正式的依赖锁定文件
- 当前没有 `Dockerfile`、`Makefile` 或 CI 构建脚本
- 当前没有正式的 lint / format 工具链
- 当前 session store 仅为内存实现，不能跨进程 / 跨重启保留
- 当前测试以 `smoke_test.py` 为主

这意味着：当前阶段应优先保持主链路清晰、边界稳定和改动可验证，而不是过早引入额外复杂度。

---

## 8. 后续补充占位

### 8.1 API 返回示例

[待确认]

### 8.2 环境变量完整说明

[待确认]

### 8.3 常见问题

[待确认]
