## 1. 文档目的

本文档描述 `prd_skill` 的系统分层、核心链路、扩展边界与稳定约束。

本文件回答：

- 系统当前是如何组织的
- 主链路是如何流动的
- 哪些边界需要长期保持稳定
- 未来扩展应该优先落在哪些层

不回答：

- 当前迭代进度
- 日常开发规则
- 任务排期
- 环境启动细节

这些内容请分别查看：

- `PRODUCT_STATE.md`
- `AGENTS.md`
- `TASKS.md`
- `README.md`

---

## 2. 系统目标

`prd_skill` 的目标是提供一条围绕 PRD 生成的可运行链路，支持：

- 多轮需求收敛
- 单次需求转 PRD
- PRD markdown 输出
- 基于 PRD 的任务拆解

当前系统重点不是覆盖大量场景，而是保持：

- 分层清晰
- 模块边界稳定
- provider 可替换
- 存储可替换
- 后续链路可扩展

---

## 3. 当前系统分层

### 3.1 API 层
文件：`app.py`

职责：

- 暴露 FastAPI 路由
- 接收请求
- 返回响应
- 统一异常映射

约束：

- 不承担业务编排
- 不承担存储逻辑
- 不承担 prompt 构造逻辑

---

### 3.2 Service 编排层
文件：`service.py`

职责：

- 管理 session 生命周期
- 执行 interactive 模式的需求收敛
- 执行 reverse 模式的单次 PRD 生成
- 执行 tasks 生成功能
- 维护主链路行为约束

约束：

- 不直接耦合具体厂商协议
- 不依赖具体 session store 实现

---

### 3.3 Schema 边界层
文件：`schemas.py`

职责：

- 定义请求模型
- 定义响应模型
- 定义领域枚举
- 定义稳定结构化边界

约束：

- 所有 API schema 集中管理
- 关键字段变化必须视为系统级变更
- 核心 schema 的变更通常会影响 service、provider 与测试链路

---

### 3.4 Prompt 层
文件：`prompts.py`

职责：

- 存放 prompt 模板
- 提供 prompt 构造函数

约束：

- 不承载业务状态流转
- 不承载接口逻辑

---

### 3.5 LLM Provider 层
文件：`llm.py`

职责：

- 定义 LLM 抽象接口
- 封装 provider 行为
- 提供 facts 抽取、下一问生成、PRD 生成能力
- 提供 JSON 提取和 schema 校验兜底

当前实现：

- `StubLLMProvider`
- `OpenAICompatibleLLMProvider`

约束：

- provider 能力通过抽象接口暴露
- service 层不感知厂商实现细节

---

### 3.6 Session Store 层
文件：`session_store.py`

职责：

- 抽象 session 存储能力
- 当前实现内存版 `InMemorySessionStore`

约束：

- future store 替换时优先保持接口稳定
- 不让上层依赖具体持久化机制

---

### 3.7 Settings 层
文件：`settings.py`

职责：

- 环境变量读取
- 配置标准化
- 配置校验

约束：

- 不把配置读取散落到业务模块

---

## 4. 当前核心链路

### 4.1 interactive 模式链路

目标：通过多轮问答逐步收敛需求，再生成 PRD。

高层流程：

1. 创建 session
2. 抽取 facts
3. 判断当前信息完整度
4. 生成下一问
5. 用户继续补充
6. 满足条件后生成 PRD
7. 基于 PRD 生成任务拆解

---

### 4.2 reverse 模式链路

目标：基于一次输入直接生成 PRD。

高层流程：

1. 接收 `mode + input_text (+ optional project_context)`
2. 进入单次 PRD 生成流程
3. 输出 markdown PRD
4. 可继续进入 tasks 生成链路

---

### 4.3 tasks 生成链路

目标：基于 PRD markdown 输出结构化任务拆解。

当前状态：

- 已具备基础能力
- 需要进一步加强测试覆盖与稳定性约束

---

## 5. 当前稳定边界与长期约束

以下内容应视为当前架构中的稳定边界：

### 5.1 路由层保持轻量
业务逻辑不下沉到 `app.py`。

### 5.2 schema 统一集中
请求、响应和领域结构集中在 `schemas.py`。

### 5.3 provider 可替换
LLM 能力通过抽象层暴露，兼容不同 provider。

### 5.4 store 可替换
当前为内存版，未来应可替换为 Redis 等持久化存储。

### 5.5 `/prd/generate` 请求形态互斥
该接口的输入约束是主链路稳定性的一部分：

- 允许仅提供 `session_id`
- 允许提供 `mode + input_text (+ optional project_context)`
- 不允许同时提供 `session_id` 和 `input_text`
- 不允许两者都不提供

### 5.6 错误响应结构统一
统一错误结构属于外部契约，不应随意变更：

```json
{
  "error_code": "STRING_CODE",
  "message": "Human readable message",
  "details": {}
}
```
## 6. 当前已知扩展方向

以下方向已预留边界，但未完全落地。

### 6.1 更多 LLM provider

**目标：**

- 支持更多兼容 OpenAI 风格或非兼容风格的 provider

**约束：**

- 优先扩展 provider 抽象层
- 不污染 `service` 层

### 6.2 持久化 session store

**目标：**

- 将 `InMemorySessionStore` 替换为 Redis 等方案

**约束：**

- 保持 store 接口稳定
- 控制对 `service` 层的影响范围

### 6.3 衔接 Codex 执行链路

**目标：**

- 将 PRD / tasks 输出继续衔接到代码执行或工程化链路

### 6.4 reverse 模式支持项目级 / 文件级输入

**目标：**

- 从更复杂输入中抽取上下文并生成 PRD

---

## 7. 当前架构中的薄弱点

- 仓库仍为根目录平铺结构，模块数量增加后可维护性会下降
- 还没有正式的测试目录与系统化测试分层
- `tasks/generate` 的覆盖度相对主链路偏弱
- 当前只支持内存 session，无法跨进程 / 跨重启保持状态
- 当前尚未引入正式 lint / format / build 体系

---

## 8. 后续架构讨论占位

### 8.1 是否保持根目录平铺

[待确认]

### 8.2 session store 的下一阶段目标实现

[待确认]

### 8.3 tasks 输出是否要进一步结构化

[待确认]

### 8.4 reverse 模式的项目 / 文件输入边界

[待确认]