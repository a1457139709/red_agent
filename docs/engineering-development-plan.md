# 工程级开发改进文档

## 1. 文档目的

本文件是后续持续开发 `mini-claude-code` 的内部工程蓝图。

目标不是解释“这个项目是什么”，而是明确：

- 后续开发应该围绕什么目标推进
- 哪些能力必须优先做
- 目录和模块应该往什么方向演化
- 每个阶段的完成标准是什么
- 开发时哪些边界不能破坏

这份文档默认面向当前项目的后续开发者，也就是后续的我自己。

## 2. 项目定位与边界

### 2.1 当前目标

本项目不是团队协作平台，也不是 SaaS Agent 服务。

当前明确目标是：

- 单人本地使用
- 主要用于开发辅助
- 支持中长时任务
- 后续逐步引入 skill 系统
- 后续引入网络安全类 skill
- 强调本地可控、安全和可维护

### 2.2 非目标

暂时不做：

- 多租户
- Web 控制台
- 用户体系
- 组织级权限模型
- 分布式调度
- 复杂云部署

结论：

后续开发应该继续在当前项目上演进，而不是推倒重来；但演进方式必须是工程化重构，而不是继续零散堆功能。

## 3. 当前基础与判断

当前代码已经具备继续演进的基础：

- 有可运行的 CLI 主链路
- 有 `Settings` 统一配置
- 有 `SessionState` 统一会话状态
- 有 `ToolExecutor` 统一工具执行边界
- 有显式工具装配
- 有基础测试和依赖清单

因此，后续重点不是“重写内核”，而是补齐四类能力：

1. 长时任务能力
2. skill / plugin 能力
3. 本地安全控制能力
4. 可维护的工程治理能力

## 4. 总体演进原则

后续开发必须遵守以下原则。

### 4.1 原则一：本地优先

任何设计都优先服务单机本地运行。

体现为：

- 优先使用本地文件和 SQLite 持久化
- 优先使用本地任务队列，而不是外部中间件
- 优先使用可读的文件配置，而不是复杂服务发现

### 4.2 原则二：Agent 核心与 skill 分离

核心运行时必须保持稳定和小。

核心只负责：

- 会话状态
- 任务状态
- 提示词拼装
- 工具执行
- 任务调度
- 安全策略

skill 不应把复杂逻辑硬塞进核心循环，应通过清晰接口接入。

### 4.3 原则三：工具必须可控

任何具备副作用的能力都必须经过统一执行层。

体现为：

- 不允许工具直接做用户交互
- 不允许工具自己决定权限模型
- 不允许工具绕过统一日志和审计

### 4.4 原则四：长时任务优先考虑可恢复性

以后引入的长时任务能力，必须优先考虑：

- 中断后可恢复
- 失败后可重试
- 每步有记录
- 可查看当前任务处于什么状态

### 4.5 原则五：安全能力不能靠 prompt 幻觉

后续做网络安全 skill 时，不能依赖“提示词要求谨慎”来保证安全。

必须通过：

- 工具级权限限制
- 命令分级
- 工作目录隔离
- 明确的 allowlist / denylist
- 结果审计

来实现真实约束。

## 5. 建议目标架构

建议逐步演化为以下结构：

```text
src/
├── main.py                     # 本地 CLI 入口
├── app/
│   ├── session_service.py      # 会话管理
│   ├── task_service.py         # 任务管理
│   ├── run_service.py          # 单次运行 orchestration
│   └── skill_service.py        # skill 装载与调用
├── agent/
│   ├── loop.py
│   ├── context.py
│   ├── prompt.py
│   ├── provider.py
│   ├── settings.py
│   └── state.py
├── runtime/
│   ├── task_runner.py          # 长时任务执行器
│   ├── checkpoint.py           # 断点保存与恢复
│   ├── event_bus.py            # 运行事件
│   └── policies.py             # 运行时策略
├── skills/
│   ├── registry.py             # skill 注册表
│   ├── base.py                 # skill 接口
│   ├── development/
│   └── security/
├── tools/
│   ├── __init__.py
│   ├── executor.py
│   ├── policies.py             # 工具权限规则
│   └── ...
├── storage/
│   ├── sqlite.py               # SQLite 访问层
│   ├── tasks.py
│   ├── sessions.py
│   └── runs.py
├── models/
│   ├── task.py
│   ├── skill.py
│   ├── run.py
│   └── events.py
└── utils/
```

说明：

- 当前不需要一步到位改成这样
- 但后续新增功能时，应尽量朝这个形态收敛

## 6. 关键能力路线图

## Phase 1：长时任务最小闭环

### 目标

让 Agent 不再只是“一问一答”的即时交互，而是能管理任务。

### 必做项

1. 定义 `Task` 数据模型
2. 定义任务状态机
3. 将一次运行与一个任务绑定
4. 支持任务日志记录
5. 支持任务中断后恢复

### 建议数据模型

`Task` 至少包含：

- `id`
- `title`
- `goal`
- `status`
- `created_at`
- `updated_at`
- `workspace`
- `last_checkpoint`
- `last_error`

建议状态：

- `pending`
- `running`
- `paused`
- `failed`
- `completed`
- `cancelled`

### 完成标准

- 能创建任务并保存到本地
- 能继续执行上次中断的任务
- 能查看任务当前状态
- 能看到任务最近几步日志

## Phase 2：skill / plugin 系统

### 目标

把“开发能力”“网络安全能力”“代码检查能力”等抽成 skill，而不是都塞进提示词或主循环。

### skill 最小结构建议

每个 skill 建议包含：

- `manifest`
- `prompt fragments`
- `tool requirements`
- `execution hooks`
- `safety constraints`
- `examples`

### skill 清单建议

优先做两类：

1. `development` skill
   - 代码阅读
   - 重构
   - 测试生成
   - 项目结构分析

2. `security` skill
   - 资产枚举
   - 漏洞初筛
   - Web 安全检查
   - 本地安全分析

### 完成标准

- skill 可以显式启用/禁用
- 不同 skill 可以影响 prompt 和工具集
- 一个任务可以绑定某个默认 skill
- skill 自己可以声明需要的工具和权限

## Phase 3：安全执行强化

### 目标

为后续网络安全 skill 做真实的本地执行保护。

### 必做项

1. 工具权限分级
2. 工作目录白名单
3. 命令 allowlist / denylist
4. 对高风险工具增加二次确认策略
5. 关键操作审计日志

### 工具权限建议

按级别划分：

- `read_only`
- `workspace_write`
- `system_command_safe`
- `system_command_sensitive`
- `network_access`

### 特别要求

网络安全 skill 后续可能会调用更多系统命令，因此必须先把执行边界建好，再扩工具。

### 完成标准

- 每个工具有明确权限级别
- 每次执行都能记录：谁触发、在哪个任务、做了什么
- 高风险命令即使是本地单用户，也要经过统一执行器

## Phase 4：本地持久化与恢复

### 目标

让 Agent 在关掉进程后还能继续任务。

### 推荐方案

首选 SQLite。

原因：

- 单机足够
- 易于查询
- 无需额外服务
- 适合任务、会话、事件日志

### 建议持久化对象

- Sessions
- Tasks
- Runs
- RunEvents
- SkillConfigs
- Checkpoints

### 完成标准

- 程序重启后可以列出历史任务
- 可以恢复未完成任务
- 可以追溯任务执行过程

## Phase 5：可观测性与调试能力

### 目标

后续开发复杂度上升后，必须有能力看清 Agent 在做什么。

### 必做项

1. 结构化日志
2. 事件流记录
3. 任务级日志文件
4. 工具调用耗时统计
5. 错误分类

### 日志建议

至少记录：

- `task_id`
- `session_id`
- `run_id`
- `step_index`
- `tool_name`
- `tool_args`
- `duration_ms`
- `status`
- `error_type`

### 完成标准

- 一个失败任务可以回放问题现场
- 可以定位是模型问题、工具问题还是权限问题

## Phase 6：网络安全 skill 引入

### 目标

在已有安全执行边界之上，逐步加入网络安全能力。

### 引入顺序建议

先加低风险能力，再加高风险能力：

1. 信息收集类
   - 指纹识别
   - 基础 HTTP 探测
   - 文件内容审计

2. 检查类
   - 常见配置错误检测
   - 依赖风险识别
   - Web 路由和暴露面分析

3. 半自动验证类
   - 仅限在本地受控目标上运行
   - 必须显式提示目标范围
   - 必须有明显的风险确认

### 禁止事项

在没有更强的工具权限治理和日志记录前，不要直接接入高危险扫描或攻击性命令。

## 7. 目录与模块演进建议

## 7.1 当前目录保留

以下模块继续保留并演进：

- `src/agent/*`
- `src/tools/*`
- `src/utils/*`
- `src/main.py`

## 7.2 新增目录优先级

建议优先新增：

1. `src/models/`
2. `src/storage/`
3. `src/app/`
4. `src/runtime/`
5. `src/skills/`

## 7.3 旧目录处理

- `test/` 保留为实验脚本区
- 规范回归测试继续放在 `tests/`

## 8. 数据模型建议

后续开发中，优先稳定以下模型。

### 8.1 Session

字段建议：

- `id`
- `created_at`
- `updated_at`
- `workspace`
- `compressed_summary`
- `metadata`

### 8.2 Task

字段建议：

- `id`
- `session_id`
- `title`
- `goal`
- `status`
- `priority`
- `workspace`
- `skill_profile`
- `created_at`
- `updated_at`

### 8.3 Run

字段建议：

- `id`
- `task_id`
- `status`
- `started_at`
- `finished_at`
- `step_count`
- `last_usage`
- `last_error`

### 8.4 SkillManifest

字段建议：

- `name`
- `version`
- `description`
- `default_prompt_fragments`
- `required_tools`
- `forbidden_tools`
- `risk_level`

## 9. 测试策略

后续测试必须分层，而不是只写集成脚本。

### 9.1 单元测试

覆盖：

- 状态对象
- 配置解析
- 安全规则
- 工具执行器
- 压缩摘要解析

### 9.2 Runtime 测试

覆盖：

- 主循环
- 多工具调用
- 最大步数
- 中断与恢复
- skill 切换

### 9.3 工具测试

覆盖：

- 文件工具
- 搜索工具
- 命令执行边界
- 权限校验

### 9.4 回归规则

每完成一个新阶段，至少新增与之对应的测试，不允许“代码已重构但无回归保护”。

## 10. 文档策略

后续必须避免再次出现“代码已变、文档还停留在旧技术栈”的情况。

建议规则：

1. 架构变更时同步更新 `docs/`
2. 新增模块时更新 `README.md`
3. 新增阶段能力时在本文件更新对应里程碑状态
4. 如果某文档只保留历史意义，必须显式标记

## 11. 开发优先级建议

如果从现在开始继续开发，建议按下面顺序推进。

### 第一优先级

- 本地任务系统
- SQLite 持久化
- 任务日志与 checkpoint

### 第二优先级

- skill 注册表
- skill manifest
- skill 与工具权限绑定

### 第三优先级

- 本地安全执行增强
- 工具权限分级
- 网络安全 skill 最小集

### 第四优先级

- 更强的可观测性
- 更完整的文档和示例

## 12. Definition of Done

后续每个阶段完成时，至少满足以下标准：

1. 有明确代码入口
2. 有回归测试
3. 有文档更新
4. 有失败场景处理
5. 不破坏现有 CLI 主链路

## 13. 下一个实际开发入口

后续开发建议从这里开始：

1. 新建 `src/models/task.py`
2. 新建 `src/storage/sqlite.py`
3. 新建 `src/storage/tasks.py`
4. 新建 `src/app/task_service.py`
5. 为任务创建、读取、继续执行补最小闭环

这是最合理的下一步，因为：

- 它直接服务长时任务目标
- 不会过早引入过重的 skill 系统复杂度
- 它能为后续网络安全 skill 提供稳定的任务承载层
