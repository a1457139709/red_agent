# RETIRED DOCUMENT

# red-code Target SPEC

## 1. Background

`red-code` 目前同时包含：

- 一个通用本地 Agent
- 一套面向红队流程的 `operation / job / evidence / finding` 运行时

当前实现已经具备较完整的底层能力，但产品形态存在几个明显问题：

- 交互以命令驱动为主，自然语言驱动不足
- 红队流程没有真正闭环，存在“创建后还要额外补执行”的割裂体验
- `task` 与 `operation` 双轨并存，用户心智混乱
- AI 参与度偏低，很多动作仍要求用户手工拆步骤
- CLI、Agent 循环、运行时编排、展示层耦合偏高，不利于后续大改

本 SPEC 定义下一阶段重构的目标产品行为与边界。

## 2. Product Positioning

`red-code` 的目标定位是：

- 以通用 Agent 为基础
- 内置红队测试能力
- 自然语言优先
- 本地优先
- 面向单用户
- 可逐步演进到 Web UI

它不是：

- 纯命令式红队工具箱
- 仅面向红队的单一产品
- 默认自动执行高风险攻击动作的平台

## 3. Product Goals

### 3.1 Primary Goals

1. 让用户通过自然语言驱动普通 Agent 与红队 Agent，而不是主要依赖 slash 命令。
2. 将当前 `task` 与 `operation` 统一为单一用户概念：`session`。
3. 让红队模式具备“从目标输入到执行到结果展示”的前台闭环体验。
4. 让 AI 在红队流程中全程参与，并自动完成低风险步骤。
5. 为后续 Web UI、计划模式、模块化扩展留下清晰分层。

### 3.2 Secondary Goals

1. 保留现有通用 Agent 的对话与基础文件操作能力。
2. 保留当前作用域校验与结构化结果能力，避免因“更易用”而失去安全边界。
3. 支持“单次临时红队动作”与“长期持久化红队任务”两种工作方式。

## 4. Non-Goals

本阶段不以以下内容为主要目标：

- 完整 Web 端实现
- 多用户协作
- 分布式 worker 集群
- 默认自动执行高风险 POC 或大规模扫描
- 为旧的 `task`/`operation` 概念做长期兼容

## 5. User Experience Principles

### 5.1 Interaction Model

- 自然语言是主入口
- slash 命令保留为调试、高级控制、运维入口
- CLI 仍是主界面
- 后续支持 Web UI，但不改变核心运行时

### 5.2 Agent Modes

系统面向用户提供两种模式：

- `normal`：普通 Agent 模式，用于日常对话、文件读写、代码工作、临时任务
- `redteam`：红队 Agent 模式，用于目标导向、可持久化、可审计的测试流程

普通用户不必理解底层 runtime 细节，但需要能明确知道自己当前处于哪种模式。

### 5.3 Clarification Strategy

对于类似“帮我看一下 example.com”这样的输入，系统应：

1. 先追问少量必要信息
2. 在拿到足够上下文后自动开始低风险步骤
3. 在高风险动作前发起确认

后续可在此基础上增加“计划模式”。

## 6. Unified Session Model

### 6.1 User-Facing Entity

未来用户只接触一个顶层概念：`session`。

`session` 表示一次由用户开启的任务上下文。它既可以是：

- 普通 Agent 的临时会话
- 红队 Agent 的持久化目标会话

### 6.2 Session Categories

系统内部至少支持两类 session：

- `normal session`
- `redteam session`

其中：

- `normal session` 默认不持久化结果
- `redteam session` 面向明确目标范围，持久化执行过程与结果

### 6.3 Relationship to Current Concepts

- 当前 `task` 将被移除
- 当前 `operation` 将被移除
- 两者职责统一收敛到 `session`

本重构不以保留旧概念为目标。

## 7. Red-Team Workflow Requirements

### 7.1 Persistent Red-Team Sessions

红队 Agent 应支持自动创建持久化 session。

用户在初始化时只需提供必要信息，例如：

- 名称
- 域名
- IP
- 授权说明或备注

不应强制用户在创建阶段手工填写：

- ports
- protocols
- tool categories
- rate limit

这些内容应降为：

- 系统默认策略
- 高级展开项
- 配置文件驱动项

### 7.2 Temporary Red-Team Actions

系统应支持无需创建持久化 session 的单次动作，例如：

- 单次 DNS 查询
- 单次 HTTP 探测
- 单次 TLS 检查
- 单次 banner 抓取
- 单次端口扫描

这些临时动作由普通 Agent 处理，默认不持久化执行结果。

### 7.3 Execution Closure

红队模式必须具备完整执行闭环：

1. AI 理解目标
2. AI 创建或恢复 redteam session
3. AI 自动生成内部执行计划
4. AI 自动创建内部执行单元
5. AI 在当前前台会话中推进执行
6. AI 实时汇报进度与结果
7. AI 能在用户要求时回顾历史记录、结果与结论

用户不应再需要手工补一个独立“运行阶段”才能真正执行。

## 8. AI Autonomy Requirements

### 8.1 Actions Allowed Automatically

在红队模式中，AI 应可自动执行以下动作：

- 创建持久化 session
- 创建内部执行单元
- 执行 DNS / HTTP / TLS / banner / port scan
- 执行重复或批量扫描多个目标
- 导出报告

### 8.2 Actions Requiring Confirmation

以下动作必须触发用户确认：

- 大规模端口扫描
- 大规模目录扫描
- POC 执行

系统必须支持将“需要确认的动作”放入配置文件，并按风险等级统一管理。

## 9. Safety Model

### 9.1 Risk-Based Confirmation

系统采用按风险等级控制确认的策略，而不是要求用户手工填写大量低层策略字段。

建议最少支持：

- `safe`
- `elevated`
- `dangerous`

其中：

- `safe` 可自动执行
- `elevated` 需要确认
- `dangerous` 需要确认，且应保留更强审计

### 9.2 Scope and Boundary

虽然用户创建 session 时应更轻量，但系统仍需保留：

- 目标范围校验
- 基本安全边界
- 高风险动作确认
- 结果记录与可追溯性

“更智能”不应等于“无边界”。

## 10. Skill and Module Model

系统应同时保留：

- 普通用户可见的 `skill`
- 红队用户更容易理解的 `module`

对用户来说可以有两套术语与呈现方式；对内部实现来说，不要求维护两套完全独立机制。

设计目标是：

- 保持扩展性
- 支持模块化能力组织
- 支持未来类似 metasploit 的模块使用体验
- 支持既可挂在持久化 session 下执行，也可独立单次执行

### 10.1 与当前 `SKILL.md` 设计的关系

当前已有的 `SKILL.md` 机制不完全匹配目标架构。

当前机制更接近：

- prompt 片段注入
- `allowed-tools` 工具可见性收窄
- 显式 `/skill` 激活
- task 绑定
- 部分 workflow skill 依赖 `operation_id`

目标架构需要的是：

- `skill` / `module` 共用的能力清单
- 参数模式
- 风险等级
- 执行方式
- 与 `session`、`ExecutionService`、确认策略和结果存储的集成

因此后续实现不应照着当前 `SKILL.md` 设计继续扩展，也不应把 `/skill plan <name> <operation_id>` 或 `/skill apply <name> <operation_id>` 作为目标架构路径。

允许复用的只有低层能力，例如：

- `SKILL.md` 作为本地能力描述文件的想法
- `allowed-tools` 收窄工具可见性的机制
- `references/` 与 `scripts/` 的目录约定

但 Phase 5 必须重新定义目标态的 skill/module manifest 与 session 执行契约。

## 11. Persistence and Storage

对于持久化 redteam session，执行结果至少分为四层：

### 11.1 `memory/`

给 AI 使用的 harness 记忆层，用于摘要、工作记忆、上下文压缩和推理辅助。

### 11.2 `artifacts/`

保存原始执行结果、探测结果、响应内容和证据原件。

### 11.3 `findings/`

保存结构化问题、结论和状态。

### 11.4 `reports/`

保存导出的面向人类的汇总结果。

重要要求：

- `memory/` 面向 AI
- 项目执行结果应单独存储，不能混成单一文件

## 12. Records and Explainability

即使底层执行采用内部 job/worker/scheduler 等机制，用户仍应能够向 AI 索要：

- 执行记录
- 已做过的步骤
- 某次扫描的结果
- 某个结论的依据

这意味着系统必须保留可解释、可检索的执行记录，但不要求用户直接面对这些底层概念。

## 13. Architecture Requirements

系统重构后必须体现清晰分层，至少满足以下要求：

- UI 层与核心运行时解耦
- Agent 循环与 CLI 控制逻辑解耦
- 工具调用与用户交互解耦
- 持久化模型与展示模型解耦
- 普通模式与红队模式在体验上可区分，在底层能力上可复用

系统应支持：

- CLI 作为当前主要入口
- Web UI 作为未来新增入口

而不要求为每个入口复制一套业务逻辑。

## 14. Priorities for the Refactor

本次架构重构优先解决以下问题：

1. 运行阶段缺失，流程不闭环
2. AI 参与度太低
3. 当前架构耦合过高，不利于后续大改

以下问题在本次重构中也应被同步改善，但优先级略低：

- operation 创建过于繁琐
- ID 导向体验不友好
- skill / module 定位不清晰
- 不利于未来 Web 化

## 15. Acceptance Criteria

当以下条件成立时，可认为目标产品方向成立：

1. 用户可以通过自然语言发起一次普通任务或红队任务。
2. 红队任务可以在前台会话中完成从初始化到执行到结果展示的闭环。
3. 用户只需提供少量必要信息即可创建持久化 redteam session。
4. `task` 与 `operation` 不再作为并列用户概念出现。
5. 高风险动作可以通过风险等级和配置文件控制确认。
6. 单次临时红队动作可以无需创建持久化 session 执行。
7. 持久化结果可以分离为 `memory/`、`artifacts/`、`findings/`、`reports/` 四层。
8. CLI 与未来 Web UI 可以共享同一套核心运行时。
