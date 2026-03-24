# 当前架构问题与改进报告

## 1. 评审范围

本报告基于当前仓库中的实际实现进行审查，重点覆盖：

- CLI 入口与会话管理
- Agent 主循环与上下文压缩
- 工具注册与工具执行
- 安全策略
- 配置、文档与工程化支撑

审查文件主要包括：

- `src/main.py`
- `src/agent/loop.py`
- `src/agent/context.py`
- `src/agent/provider.py`
- `src/tools/*.py`
- `src/utils/*.py`
- `docs/*.md`

## 2. 总体结论

当前项目的优点是结构直观、教学意图清晰、最小链路完整，已经具备一个本地 Code Agent 的基本骨架。

但从“可持续演进”的角度看，当前架构仍有几类明显问题：

1. 运行态状态管理不稳定，已经存在会导致下一轮对话报错的实现缺陷
2. Agent 主循环对多工具调用、异常边界和终止条件的处理不够完整
3. 工具层和 CLI 展示层耦合较重，不利于复用、测试和后续服务化
4. 安全策略仍是演示级，尤其在 Windows 环境下覆盖不足
5. 文档与实际代码已经出现明显漂移，容易误导后续维护者
6. 工程化基础薄弱，缺少依赖清单、自动化测试和结构化可观测性

如果继续在当前基础上叠加功能，后续维护成本会快速上升。建议先做一轮“稳定性与边界治理”，再扩展能力。

## 3. 主要问题清单

## 3.1 会话状态类型不一致，压缩后可能直接失效

### 现象

`src/main.py` 中 `context_summary` 的类型在不同路径里并不一致：

- 初始化时是字符串：`context_summary = ""`
- `/reset` 后被置为空列表：`context_summary = []`
- 压缩完成后被置为列表：`context_summary = [hint]`

而 `src/agent/prompt.py` 中 `assemble_system_prompt(extra_prompt: str)` 明确按字符串来拼接提示词。

### 影响

- 一旦执行过压缩，下一轮进入 `prompt += FORMAT_PREFIX + extra_prompt + "\n\n"` 时，`extra_prompt` 可能是列表，存在直接抛出类型错误的风险
- 会话状态没有统一模型，后续想加入更多状态字段时会进一步混乱

### 根因

- 运行态状态由 `history`、`context_summary` 两个松散变量维护，没有统一的会话状态对象
- 类型约束只存在于注释和函数签名，没有在状态流转中被真正保持

### 建议

- 引入 `ConversationState` 或 `SessionState` 数据结构，统一管理：
  - `history`
  - `compressed_summary`
  - `last_usage`
  - `step_count`
- 约束 `compressed_summary` 始终为 `str | None`
- 将压缩前后的状态切换封装到单独方法里，避免在 `main.py` 中手工散落赋值

## 3.2 Agent 主循环对多工具调用的消息回填方式不正确

### 现象

`src/agent/loop.py` 在 `for tool_call in AI_message.tool_calls:` 循环内部，每处理一个工具调用都会重复执行：

- `messages.append(AI_message)`
- `steps.append(AI_message)`

这意味着如果模型一次返回多个工具调用，同一个 `AIMessage` 会被重复插入多次。

### 影响

- 会重复污染消息历史
- 造成无意义的上下文膨胀
- 可能让模型在下一轮看到错误的执行轨迹
- 调试日志和历史压缩结果也会被重复信息干扰

### 根因

- 当前循环把“追加 assistant 消息”和“处理 tool_call”混在了一起
- 没有区分“一条 assistant 消息”与“多条 tool result”的正确结构

### 建议

- 调整为：
  1. 先将 `AI_message` 追加一次
  2. 再遍历所有 `tool_call`
  3. 为每个工具调用追加一条 `ToolMessage`
- 将“消息拼接”和“工具执行”分拆成独立函数，降低循环体复杂度

## 3.3 缺少最大步数兜底返回，异常边界不完整

### 现象

`src/agent/loop.py` 中存在 `MAX_AGENT_STEPS = 50`，但当循环跑满仍未结束时，函数没有明确返回值。

### 影响

- `agent_loop()` 可能返回 `None`
- `main.py` 中直接访问 `result["response"]` 时会触发二次错误
- 用户无法区分是“任务未完成”还是“程序异常”

### 建议

- 在达到步数上限时返回结构化失败结果，例如：
  - `status = "max_steps_exceeded"`
  - `response = "任务未在步数限制内完成"`
  - `messages = steps`
- 在 CLI 层统一处理失败态，而不是依赖通用 `except Exception`

## 3.4 工具层与 CLI 展示层耦合过深

### 现象

多个工具模块直接依赖 `agent.logger.ColoredOutput`，如：

- `src/tools/readFile.py`
- `src/tools/writeFile.py`
- `src/tools/editFile.py`
- `src/tools/deleteFile.py`
- `src/tools/bash.py`

此外，`bash` 工具内部还直接调用 `confirm_from_user()`，把交互式确认写死在工具执行层。

### 影响

- 工具无法脱离 CLI 独立复用
- 不方便做服务化封装、接口层接入或自动化测试
- 将来如果接 Web UI、API 或批处理模式，会遇到交互阻塞和日志输出混乱

### 根因

- 当前工具层承担了业务执行、风险提示和终端展示三类职责

### 建议

- 将工具层改成“纯执行层”，只返回结构化结果，例如：
  - `status`
  - `output`
  - `warnings`
  - `requires_confirmation`
- 由上层 Runtime 或 CLI 决定如何展示和确认
- 引入 `ToolExecutor` 统一处理日志、确认、异常包装和超时控制

## 3.5 安全策略对 Windows 环境覆盖明显不足

### 现象

`src/utils/safety.py` 的危险命令规则几乎都以 Unix 命令为主，例如：

- `rm -rf`
- `dd`
- `mkfs`
- `/dev/sda`
- `shutdown|reboot|halt`

而当前项目运行环境是 Windows/PowerShell，本地实际常见高风险命令如以下类型并未覆盖：

- `del`
- `Remove-Item`
- `rd /s`
- `format`
- PowerShell 管道脚本执行

同时，`src/tools/bash.py` 仍使用 `subprocess.run(..., shell=True)` 执行原始命令字符串。

### 影响

- 当前“安全机制完善”的结论并不成立，只能算演示级防护
- 在 Windows 环境下，误删或危险脚本执行的拦截效果有限

### 建议

- 按平台拆分安全策略：
  - Windows 命令规则
  - Unix 命令规则
- 将命令解析从简单正则升级为“命令分类 + 风险等级”
- 对 shell 执行增加：
  - 超时
  - 最大输出
  - 工作目录限制
  - 可选白名单或能力开关

## 3.6 `search` 工具绕过了路径安全边界

### 现象

`src/tools/search.py` 直接使用 `Path(file_path).rglob("*")` 搜索文件，没有走 `resolve_safe_path()`。

### 影响

- 可以通过传入 `..` 或绝对路径等方式搜索工作目录之外的内容
- 与其他文件类工具的安全边界不一致
- 实际上破坏了“所有文件操作都受工作目录约束”的设计前提

### 建议

- 统一让 `search` 先走 `resolve_safe_path()`
- 补充搜索深度、文件数、总结果数、总字符数限制
- 对二进制文件和大目录做跳过策略

## 3.7 上下文压缩实现较脆弱，缺少可验证的状态契约

### 现象

`src/agent/context.py` 中的压缩逻辑存在几个问题：

- `compress_context()` 虽然是异步函数，但内部调用的是同步 `model.invoke(...)`
- 压缩输出只是自由文本/XML 片段，没有做结构校验
- 压缩摘要直接拼回提示词，没有明确的状态对象承载

### 影响

- 会阻塞异步主流程
- 压缩结果一旦格式漂移，后续提示词质量不可控
- 很难测试“压缩后还能否稳定续跑”

### 建议

- 为压缩结果定义明确结构，例如 dataclass / pydantic schema
- 使用真正的异步模型调用
- 将“压缩摘要生成”和“摘要注入提示词”拆开
- 为压缩逻辑增加单元测试和回归样例

## 3.8 配置层过薄，模型与运行参数不可治理

### 现象

`src/agent/provider.py` 直接从环境变量读取：

- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `OPENAI_MODEL`

同时还硬编码了 `temperature=0.5`。当前没有：

- 配置校验
- 默认值策略
- 多环境配置
- 超时、重试、日志等级等运行参数

### 影响

- 配置错误只能在运行时暴露
- 不利于多模型切换或不同部署环境复用
- 参数分散，后续扩展会越来越难维护

### 建议

- 引入统一配置模块，例如 `settings.py`
- 使用 `pydantic-settings` 或同类方案做配置校验
- 把模型参数、步数限制、工作目录、安全级别统一纳入配置

## 3.9 工具注册依赖 import 副作用，扩展边界不够清晰

### 现象

`src/tools/__init__.py` 会在导入阶段自动扫描并 import 全部工具模块，再由 `registry.py` 的全局字典收集工具。

### 影响

- 工具注册依赖 import 顺序和模块副作用
- 单元测试时不容易按需加载工具
- 将来如果希望按配置启用/禁用工具，会比较别扭

### 建议

- 将“发现工具”和“启用工具”拆开
- 用显式 `build_tool_registry(config)` 替代全局可变字典
- 支持按环境启用工具集，例如：
  - `safe_tools`
  - `fs_tools`
  - `network_tools`

## 3.10 文档已经和实际实现发生漂移

### 现象

`docs/overview.md`、`docs/agent-loop.md` 等文档仍在描述：

- Bun + TypeScript
- Vercel AI SDK
- 七牛 Provider
- `generateText`

但当前真实实现已经是：

- Python
- LangChain
- `langchain_openai.ChatOpenAI`
- 本地 `tool.invoke(...)` 主循环

### 影响

- 新接手的人会先建立错误认知
- 文档失去“架构事实来源”的作用
- 后续讨论和重构容易建立在错误前提上

### 建议

- 区分“历史设计文档”和“当前实现文档”
- 给 `docs/` 增加状态标记：
  - `current`
  - `legacy`
  - `planned`
- 将当前真实架构以代码为准重新整理

## 3.11 缺少依赖清单与自动化测试，工程闭环不完整

### 现象

当前仓库中没有发现：

- `requirements.txt`
- `pyproject.toml`
- `pytest` 测试套件
- CI 检查流程

`test/` 目录更像实验脚本集合，不是稳定的自动化验证体系。

### 影响

- 新环境复现成本高
- 代码改动缺少回归保护
- 难以放心做架构重构

### 建议

- 补齐依赖清单
- 建立最基础的 `pytest` 用例，优先覆盖：
  - 路径安全
  - 工具注册
  - Agent loop 的多工具调用
  - 上下文压缩前后状态切换
- 加入格式化、静态检查与基础 CI

## 3.12 还有若干实现细节会放大维护成本

### 例子

- `src/tools/editFile.py` 成功返回值尾部多了一个逗号，实际返回的是元组而不是字符串
- `src/agent/loop.py` 中 `system_prompt` 以普通字符串加入消息列表，而不是显式 `SystemMessage`
- `src/tools/readFile.py` 通过 `readlines()` 全量读取后再切片，大文件场景扩展性一般
- `src/main.py` 的异常处理过于宽泛，错误只会落成 `print(f"Error: {e}")`

### 建议

- 在稳定性修复阶段一并清理这些“非架构但会持续制造噪音”的问题

## 4. 改进优先级建议

## P0：先修会影响正确性的项

建议优先处理：

1. 修复 `context_summary` 类型不一致问题
2. 修复多工具调用时 `AIMessage` 被重复追加的问题
3. 为 `MAX_AGENT_STEPS` 补明确失败返回
4. 修复 `search` 未走安全路径的问题
5. 修复 `edit_file` 返回元组的问题
6. 补 Windows 命令安全规则

这一阶段的目标是：先让系统在当前边界内“稳定可跑”。

## P1：做结构治理，降低后续重构成本

建议处理：

1. 引入统一 `SessionState`
2. 引入统一 `Settings`
3. 把工具执行、日志展示、用户确认从工具函数中解耦
4. 将工具注册从 import 副作用改成显式装配
5. 重构上下文压缩为可验证的结构化流程

这一阶段的目标是：让代码开始具备真正的可扩展性。

## P2：补工程化闭环

建议处理：

1. 补 `requirements.txt` 或 `pyproject.toml`
2. 建立 `pytest` 基础测试集
3. 增加日志、追踪和错误分类
4. 清理并重写失真的设计文档

这一阶段的目标是：让项目可以稳定迭代，而不是只能手工试跑。

## 5. 推荐的目标架构

建议逐步收敛为以下分层：

```text
CLI / UI Layer
  └── 负责输入输出、渲染、用户确认

Application Layer
  └── SessionState、Settings、Use Cases

Agent Runtime Layer
  └── prompt assembly、loop orchestration、context compression

Tool Execution Layer
  └── tool executor、permission check、timeout、result wrapping

Tool Layer
  └── read_file、edit_file、bash、search ...

Infrastructure Layer
  └── model provider、filesystem、logging、env config
```

对应原则：

- 状态统一收口到 Application Layer
- 工具只做执行，不负责展示
- 安全与权限由 Tool Execution Layer 统一处理
- 文档以“当前实现”为准，不再混合历史方案

## 6. 建议的落地顺序

第一周：

- 修 P0 问题
- 补依赖清单
- 补最基础单测

第二周：

- 引入 `SessionState` 与 `Settings`
- 抽出 `ToolExecutor`
- 重构多工具回填逻辑

第三周：

- 重写 `docs/` 中的当前架构文档
- 增加结构化日志和错误分类
- 评估是否引入更清晰的 Agent Runtime 抽象

## 7. 结论

这个项目现在最大的价值，在于它已经把一个 Code Agent 的最小闭环搭出来了；最大的风险，在于“演示代码”与“可维护架构”之间还隔着一层治理工作。

建议不要直接继续往上堆新工具，而是先完成一轮稳定性和边界重构。这样后面无论是接入更多工具、做 Web 化、做多 Agent，还是把它升级成更正式的开发助手，都会顺很多。
