# AGENTS.md

## 1. 作用

本文件用于约束 AI 编程工具和开发者在本仓库中的工作方式。

目标：

- 保持改动范围可控
- 保持实现风格一致
- 保持改动可验证、可回滚
- 减少 AI 生成代码偏离项目现状的概率

项目背景、架构细节、当前状态、历史决策、任务清单请分别查看：

- `README.md`
- `ARCHITECTURE.md`
- `PRODUCT_STATE.md`
- `DECISIONS.md`
- `TASKS.md`

---

## 2. 开始修改前必须做的事

在开始任何修改前，至少先阅读：

1. `README.md`
2. `AGENTS.md`
3. `TASKS.md` 中对应任务
4. 与本次任务直接相关的代码文件
5. 如涉及主链路、稳定边界或扩展方向，再查看 `ARCHITECTURE.md`

如未理解当前任务边界，不要直接重构。

---

## 3. 工作原则

1. 优先做最小改动，不做无明确要求的大范围重构。
2. 优先复用现有模块、现有 schema、现有流程。
3. 不新增超出当前项目阶段的复杂度。
4. 代码完成不等于任务完成；验证和文档同步后才算完成。
5. 如改动会影响接口、主链路或已有行为，必须在说明中明确写出影响范围。
6. 不确定的地方先保留占位，不自行假设并扩散实现。

---

## 4. Git 协作规范

### 4.1 基本原则

- 每次改动应尽量围绕单一目标展开，避免一次提交混入多个不相关修改。
- 开始修改前先查看当前工作区状态，避免覆盖未提交改动。
- 不要顺手改动与当前任务无关的文件。
- 不要在一次改动中同时做“功能新增 + 大范围重构 + 风格清洗”。

### 4.2 分支规范
分支命名建议使用：

- `feature/<name>`
- `fix/<name>`
- `refactor/<name>`
- `docs/<name>`
- `test/<name>`

示例：

- `feature/interactive-facts-refine`
- `fix/prd-generate-validation`
- `docs/update-architecture`

`[待确认：是否补充主分支保护规则，例如禁止直接提交 main]`

### 4.3 提交规范

commit message 建议使用以下结构：

```text
<type>: <简明标题>

- <改动对象> <改动动作>
- <改动对象> <改动动作>
- <改动对象> <改动动作>
```

要求

- 标题行使用以下类型之一：
  - `feat:`
  - `fix:`
  - `refactor:`
  - `docs:`
  - `test:`
  - `chore:`
- 标题应写清楚“本次改动的核心目标”，避免空泛表达，例如：
  - `update docs`
  - `fix issues`
  - `cleanup code`
  - `add changes`
- 正文建议补充 3～5 条 bullet，概括本次主要改动点
- 每条 bullet 尽量保持简洁，聚焦“改了什么”
- bullet 描述优先写“改动对象”，再写“改动动作”；必要时再补充结果或目的
- 若改动非常小，可只写标题；若改动涉及多个相关点，应补充 bullet
- bullet 应覆盖本次提交的主要内容，不要写无关背景，不要复制测试日志

推荐标题示例

- `feat: 为 interactive v2 接入真实 LLM provider`
- `fix: 修正 /prd/generate 的互斥校验逻辑`
- `docs: 补充架构边界与项目状态说明`
- `refactor: 拆分 workflow 路由与编排职责`
- `test: 增加 repair 链路的回归覆盖`

推荐正文示例
```text
feat: 为 prd_skill interactive v2 接入真实 LLM provider

- provider 层新增 openai-compatible 实现
- provider 选择逻辑支持基于环境变量切换 stub / real provider
- 响应处理链路增加 JSON 解析、schema 校验与上游异常处理
- llm 与 prompts 依赖关系修正循环引用问题
- 冒烟测试补充 provider 装配层、行为层与 API 主链路覆盖
```

### 4.4 提交前最低要求

提交前至少检查：

1. `git status`
2. `git diff --stat`
3. 当前改动是否只覆盖本次任务范围
4. 当前改动是否包含临时代码、调试输出、无关格式化修改
5. 当前改动说明是否写清楚“改了什么、为什么改、如何验证”

---

## 5. 代码规范

### 5.1 通用要求

- 使用 Python 3.11+ 语法。
- 使用完整类型注解。
- 公开类、公共函数和非平凡函数写简洁 docstring。
- 命名使用 `snake_case`，类名使用 `PascalCase`。
- 使用 4 空格缩进。
- 尽量保持单一职责，避免超长函数和过深嵌套。

### 5.2 代码组织要求

- 不在不相关文件中定义请求/响应 schema。
- 不在业务代码中散落 prompt 文本。
- 不在实现中扩散具体厂商协议细节。
- 不将临时调试逻辑、一次性脚本、注释掉的大段旧代码混入正式实现。

### 5.3 错误处理要求

- 错误要显式抛出，不要吞异常。
- 不返回结构不稳定的错误格式。
- 出现异常路径时，优先保持现有错误处理风格一致。

### 5.4 修改风格要求

- 优先局部修改，而不是整块重写。
- 优先修正现有实现，不轻易新增并行方案。
- 如需调整命名、字段或结构，应先确认影响范围，再同步修改相关代码和测试。

---

## 6. 修改后最低要求

提交前至少完成：

1. 检查改动是否超出任务范围
2. 检查关键链路是否仍可运行
3. 检查相关 schema / provider / 测试是否已同步
4. 如行为发生变化，更新对应文档
5. 在任务说明或提交说明中写清：
   - 改了什么
   - 为什么改
   - 如何验证
   - 是否还有未完成项

当前主要测试入口：

```bash
python smoke_test.py
```

语法级检查可执行：

```bash
python -m compileall .
```

## 7. 常见联动检查

以下情况通常需要联动检查，不要只改一个文件后就结束。

### 7.1 修改核心 schema 时

通常至少检查：

- `schemas.py`
- `service.py`
- `llm.py`
- `smoke_test.py`

适用对象包括但不限于：

- `GeneratePrdRequest`
- `SessionState`
- `ExtractedFacts`
- `FactExtractionResult`
- `OpenQuestion`

### 7.2 修改 provider 行为时

通常至少检查：

- `llm.py`
- `service.py`
- `smoke_test.py`

并确认：

- `StubLLMProvider` 仍可稳定本地运行
- `OpenAICompatibleLLMProvider` 仍兼容当前 JSON 提取与 schema 校验逻辑

### 7.3 修改主链路时

通常至少检查：

- 请求校验
- 响应结构
- 错误路径
- 冒烟测试覆盖
- 对应文档说明

---

## 8. 禁止事项

- 不要把业务逻辑写进 `app.py`
- 不要把 prompt 文本散落到 `service.py` 或路由层
- 不要修改统一错误响应结构而不更新相关文档与测试
- 不要忽略 `/prd/generate` 的关键输入约束
- 不要在 `service.py` 中写死厂商协议细节
- 不要新增破坏性字段改名而不更新相关代码和测试
- 不要假设当前 session 能跨重启保留
- 不要误覆盖工作区未提交改动
- 不要把真实密钥、敏感配置或测试用秘密信息写入仓库