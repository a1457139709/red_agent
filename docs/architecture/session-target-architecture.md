# Session-Centric Target Architecture

## 1. Purpose

本文档描述 `red-code` 下一阶段重构的目标架构。

它不是当前实现说明，而是基于已确认需求形成的目标态设计，服务于后续的 `session` 化重构、自然语言优先交互、红队闭环执行与未来 Web UI 扩展。

## 2. Design Goals

目标架构需要同时满足：

- 保留通用 Agent 能力
- 提升红队 Agent 的自动化程度
- 用统一的 `session` 心智替代 `task` / `operation`
- 以前台同步执行为主，体验接近 Claude Code
- 保留内部执行记录与可追溯性
- 降低 CLI、展示层、Agent 循环、执行引擎之间的耦合
- 为后续 Web UI 和计划模式预留边界

## 3. Top-Level Product Shape

未来产品形态由一个主 Agent 提供两种运行模式：

- `normal mode`
- `redteam mode`

两种模式共享一套底层能力，但在以下方面不同：

- 默认是否持久化
- 可见工具与模块
- 安全确认策略
- 结果存储方式

## 4. Core User Concept: Session

### 4.1 Single Top-Level Entity

未来用户只接触 `session`。

`session` 是所有任务的统一容器，用来表示一次由用户开启、由 AI 持续理解和推进的工作上下文。

### 4.2 Session Types

内部至少支持：

- `normal`
- `redteam`

建议在模型中加入：

- `persistence_mode`
- `goal`
- `targets`
- `status`
- `mode`
- `created_at`
- `updated_at`

### 4.3 Persistence Rules

- `normal session` 默认不持久化红队结果
- `redteam session` 默认持久化
- 临时红队动作走 `normal mode`，不自动落库

## 5. Target Layering

目标分层如下：

```text
UI Adapters
  |- CLI Adapter
  |- Web Adapter (future)

Agent Controller
  |- mode routing
  |- clarification flow
  |- plan / execute / summarize loop

Application Services
  |- Session Service
  |- Execution Service
  |- Module Service
  |- Memory Service
  |- Artifact / Finding / Report Service
  |- Confirmation Policy Service

Execution Engine
  |- synchronous foreground runner
  |- internal job orchestration
  |- scheduler / worker / queue primitives
  |- scoped tool execution

Persistence
  |- session store
  |- memory store
  |- artifact store
  |- finding store
  |- report store
  |- execution log store
```

关键原则：

- UI 只负责输入输出与展示
- Agent Controller 负责理解用户意图并驱动服务
- Application Services 负责业务规则
- Execution Engine 负责真正执行
- Persistence 负责状态和结果保存

## 6. UI Adapters

### 6.1 CLI Adapter

CLI 仍然是当前主入口。

但其职责应收缩为：

- 接收自然语言输入
- 显示 AI 的澄清问题、进度和结果
- 提供少量高级 slash 命令
- 展示历史记录与持久化结果

CLI 不应继续承担：

- 复杂实体装配
- 业务流程编排
- 直接控制内部执行状态机

### 6.2 Web Adapter

未来 Web UI 应与 CLI 共用同一套服务层。

目标形态是聊天视图与管理台双视图并存：

- 聊天视图负责自然语言工作流
- 管理台负责 session / artifacts / findings / reports 浏览

## 7. Agent Controller

Agent Controller 是未来运行时的真正入口协调层。

它负责：

- 识别当前是普通模式还是红队模式
- 在信息不足时发起最少必要澄清
- 决定本次任务是否需要创建持久化 redteam session
- 驱动计划、执行、汇报循环
- 在需要时调用确认策略
- 对用户请求的“查看记录”“导出结果”“继续执行”做统一路由

### 7.1 Clarification Rule

当用户输入目标不完整时，先追问少量必要信息，再继续执行。

例如：

- 目标是域名还是 IP
- 是否是一次长期跟踪任务
- 是否已有授权说明

### 7.2 Plan-Then-Execute Direction

默认交互为：

1. clarify
2. derive intent
3. choose mode
4. execute low-risk steps
5. summarize and ask for confirmation when needed

未来可在此基础上增加显式计划模式，但不作为第一阶段前置条件。

## 8. Session Service

Session Service 统一替代当前 `task` 与 `operation` 的顶层职责。

它负责：

- 创建 session
- 恢复 session
- 更新状态
- 维护目标范围
- 暴露用户友好的会话标识
- 维护会话摘要与元数据

### 8.1 User-Friendly Labels

虽然内部仍可保留 UUID 和内部键，但用户侧应优先使用：

- 标题
- 模式
- 目标摘要
- 最近更新时间

用户不应被迫以 `job_id`、`finding_id` 为主要交互入口。

## 9. Module and Skill Service

未来内部保留统一扩展机制，但对外允许两种呈现：

- `skill`
- `module`

建议职责如下：

- `skill`：通用 Agent 能力增强
- `module`：红队能力单元与工作流模板

两者底层都应支持：

- 元数据
- 可见工具限制
- 风险等级
- 参数模式
- 单次执行
- 挂接到持久化 redteam session

## 10. Execution Architecture

### 10.1 Foreground-First Execution

第一优先体验是前台同步执行。

用户在当前会话中应看到：

- AI 正在做什么
- 当前在执行哪个步骤
- 结果是什么
- 为什么暂停等待确认

这与当前“先创建，再额外补运行”的流程不同。

### 10.2 Internal Job Engine

虽然用户不直接面对 job/runtime 概念，但内部建议继续保留：

- job
- worker
- scheduler
- scoped execution

保留原因：

- 可追溯执行记录
- 可恢复与可扩展性
- 未来后台化与 Web 化基础

但这些概念应下沉到内部执行引擎，不再塑造用户心智。

### 10.3 Execution Recordability

内部执行引擎必须能保留：

- 做过哪些步骤
- 每一步的输入与输出摘要
- 哪些步骤失败
- 哪些步骤需要确认
- 哪些结果形成了 artifact 或 finding

用户可以通过 AI 语言接口索要这些记录。

## 11. Safety and Confirmation

### 11.1 Policy Direction

目标架构采用风险等级驱动的确认机制，而不是让用户在创建 session 时填写大量底层约束。

### 11.2 Risk Levels

最少支持：

- `safe`
- `elevated`
- `dangerous`

建议默认映射：

- `safe`
  - DNS
  - HTTP probe
  - TLS inspect
  - banner grab
  - 小规模 port scan
- `elevated`
  - 大规模端口扫描
  - 大规模目录扫描
- `dangerous`
  - POC 执行

### 11.3 Configuration

需要确认的动作应通过配置文件定义，而不是硬编码在 CLI 流程中。

配置至少需要描述：

- 风险等级
- 默认确认策略
- 可覆写的模块或动作名

## 12. Storage Architecture

持久化 redteam session 的数据应分为四层。

### 12.1 `memory/`

仅供 AI harness 使用，用于：

- 工作记忆
- 会话摘要
- 历史压缩
- 稳定事实抽取

### 12.2 `artifacts/`

保存原始执行结果与证据原件，例如：

- DNS 结果
- HTTP 响应
- TLS 信息
- 端口扫描结果

### 12.3 `findings/`

保存结构化结论与状态，例如：

- 标题
- 目标
- 严重程度
- 置信度
- 状态
- 关联 artifacts

### 12.4 `reports/`

保存导出结果和面向人的视图。

## 13. Normal Mode vs Red-Team Mode

### 13.1 Normal Mode

适合：

- 日常 Agent 使用
- 文件读写
- 代码操作
- 单次临时探测

特点：

- 默认不持久化红队结果
- 更像当前基础 Agent

### 13.2 Red-Team Mode

适合：

- 持续性的目标测试
- 需要记录与结果管理的任务
- 需要 artifacts / findings / reports 的场景

特点：

- AI 自动创建和维护持久化 session
- AI 自动推进低风险步骤
- 高风险动作触发确认

## 14. Mapping from Current Runtime

### 14.1 To Be Removed from User Model

以下概念应从用户侧消失：

- `task`
- `operation`

### 14.2 To Be Preserved Internally

以下能力应尽量复用：

- scope validation
- typed security tools
- structured evidence pipeline
- worker / scheduler / job primitives
- session memory compression ideas

### 14.3 To Be Rewritten or Split

以下区域预计需要大改：

- CLI routing
- top-level command model
- task/operation dual service model
- user-facing identifier model
- execution closure

## 15. Migration Direction

建议按以下方向推进重构：

### Phase 1. Documentation and Contracts

- 明确目标 SPEC
- 明确 session-centric target architecture
- 定义风险配置契约

### Phase 2. Session Model Introduction

- 引入统一 `session`
- 删除 `task` / `operation` 双顶层用户概念
- 建立新服务接口

### Phase 3. Foreground Execution Closure

- 增加前台同步执行闭环
- 将内部 job engine 下沉为实现细节

### Phase 4. Module/Skill Unification

- 统一 skill/module 元数据与运行时
- 调整用户侧术语呈现

### Phase 5. Storage Refactor

- 拆分 memory / artifacts / findings / reports
- 建立用户可检索的执行记录

### Phase 6. Web Adapter

- 在不改变核心服务层的前提下接入 Web UI

## 16. Acceptance Criteria

目标架构应至少支持以下结果：

1. 用户可以通过自然语言启动普通任务或红队任务。
2. 红队任务可以在前台完成闭环执行。
3. 持久化顶层对象统一为 `session`。
4. 临时红队任务可以不持久化执行。
5. 高风险动作可以通过风险等级配置触发确认。
6. 用户可以通过 AI 查询执行记录与结果。
7. CLI 与未来 Web UI 共用同一套服务层和执行引擎。
