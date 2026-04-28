# Control Center 改造方案

## 1. Purpose

本文档定义 `red-code` 从当前代码库演进到“独立桌面客户端 + App Server + 实时控制台”的详细改造方案。

它不是高层路线图，而是面向工程实施的细化方案。文档目标是做到：

- 明确当前基线
- 明确目标结构
- 明确分阶段实施顺序
- 明确每个阶段需要新增或重写的模块
- 明确接口、状态模型、测试与验收标准

## 2. Current Baseline

### 2.1 已存在可复用能力

当前仓库已经具备以下关键基础：

- `SessionInteractionService`
  - 位于 `src/app/session_interaction_service.py`
  - 负责构造 `ControllerRequest`、路由 controller、触发 execution
- `InteractionPort`
  - 位于 `src/app/interaction_port.py`
  - 已具备 transport-neutral 的交互输出接口
- `ConversationContext`
  - 位于 `src/models/conversation_context.py`
  - 已从 CLI `ShellState` 中抽出共享交互状态
- `Web DTO and Serialization`
  - 位于 `src/web/contracts.py` 与 `src/web/serialization.py`
  - 已具备 Web 侧数据表达能力
- `WebInteractionAdapter`
  - 位于 `src/web/interaction_adapter.py`
  - 已具备 conversation store、event queue、confirmation 等服务化雏形
- `ExecutionService`
  - 已支持 foreground execution、progress event、confirmation bridge
- `SessionService`
  - 已是 session-centric 业务主入口
- `SessionRecordQueryService`
  - 已支持历史、steps、artifacts、findings、reports 查询
- `ReportFlowService`
  - 已支持 report 生成/复用
- `DashboardService`
  - 已具备 session dashboard 聚合能力
- `runtime/orchestration`
  - 已具备 worker、scheduler、job runtime、scope validation 等基础

### 2.2 当前缺口

当前仓库仍然缺少：

- 真正的常驻 App Server 入口
- 正式 HTTP API
- 正式 WebSocket server
- 独立桌面客户端工程
- 连接管理与 operator 连接模型
- 完整的 approval queue 与 reconnect 语义
- 可直接用于 GUI 大屏的 dashboard/event feed API
- detached/background execution 的主产品路径
- 服务部署、配置、认证、打包和运维脚本

### 2.3 当前核心约束

必须保留：

- Python 作为 agent/runtime 主体
- 现有 session-centric 服务边界
- 安全确认和 scope 验证逻辑
- SQLite + 本地文件的最小可用部署模式

不能采用：

- 把服务端重写为 Node/TypeScript
- 直接绕过现有 service 层做 GUI 版专用逻辑
- 在桌面客户端实现风险裁决或结果生成逻辑

## 3. Target Repository Shape

改造完成后的推荐目录布局如下：

```text
src/
  server/
    app.py
    dependencies.py
    lifecycle.py
    auth.py
    ws.py
    routes/
      health.py
      sessions.py
      reports.py
      dashboard.py
      approvals.py
      artifacts.py
  app/
    session_interaction_service.py
    interaction_port.py
    conversation_service.py
    approval_service.py
    event_stream_service.py
    connection_service.py
  web/
    contracts.py
    serialization.py
    conversation_store.py
    interaction_adapter.py
  runtime/
  orchestration/
  storage/

desktop-client/
  src/
    app/
    features/
      dashboard/
      sessions/
      timeline/
      findings/
      artifacts/
      reports/
      approvals/
      connections/
    lib/
      api/
      ws/
      state/
      types/
  src-tauri/
```

## 4. Design Principles

改造必须遵守以下原则：

### 4.1 先服务化，再 GUI 化

先把当前 Python runtime 提升为常驻服务，再开发桌面客户端。否则客户端会围绕 CLI 细节构建，后续会返工。

### 4.2 前台与后台执行并存

系统必须同时支持：

- 当前交互里的前台执行
- 客户端断开后继续运行的后台执行

不能把产品完全绑定在单个 CLI shell 的生存期上。

### 4.3 客户端只做显示与操控

风险判定、工具执行、finding/report 生成都必须在后端。

### 4.4 先单节点，后扩展

v1 优先完成：

- 单用户
- 单 App Server
- 单 worker
- SQLite/文件系统

而不是一开始引入复杂基础设施。

### 4.5 兼容现有 CLI，但不让 CLI 阻碍新架构

CLI 可在迁移期继续存在，但不得继续成为主产品路径的唯一入口。

## 5. Target Runtime Responsibilities

### 5.1 Desktop Client

固定职责：

- 连接管理
- 当前工作区展示
- timeline 与 dashboard
- approval/clarification 输入
- artifact/finding/report 浏览
- 本地连接配置缓存

### 5.2 App Server

固定职责：

- HTTP API
- WebSocket gateway
- connection/conversation 管理
- 调用 `SessionInteractionService`
- 路由查询服务
- approval 状态管理
- audit logging

### 5.3 Runtime Layer

固定职责：

- foreground interactive execution
- detached/background execution
- scheduler/worker/job lifecycle
- tool execution
- progress and event emission

### 5.4 Persistence

固定职责：

- session、run、job、event、approval 元数据存储
- artifact/report 文件存储
- finding/report 查询基础

## 6. HTTP and WebSocket Contract

### 6.1 HTTP Endpoint Families

v1 固定实现：

- `POST /api/connections`
- `GET /api/health`
- `GET /api/sessions`
- `GET /api/sessions/{session_identifier}`
- `GET /api/sessions/{session_identifier}/history`
- `GET /api/sessions/{session_identifier}/steps`
- `GET /api/sessions/{session_identifier}/artifacts`
- `GET /api/sessions/{session_identifier}/findings`
- `GET /api/sessions/{session_identifier}/reports`
- `GET /api/sessions/{session_identifier}/dashboard`
- `POST /api/sessions/{session_identifier}/reports`
- `GET /api/approvals`
- `POST /api/runs/{run_id}/cancel`

说明：

- 查询和下载走 HTTP
- dashboard 初始加载与分页也走 HTTP
- 生成报告通过 HTTP 触发，结果仍可通过事件推送更新

### 6.2 WebSocket 消息族

#### client -> server

- `conversation.message`
- `conversation.answer_clarification`
- `conversation.confirmation`
- `conversation.cancel_run`
- `session.bind`
- `session.unbind`

#### server -> client

- `controller.result`
- `execution.progress`
- `clarification.required`
- `confirmation.required`
- `confirmation.resolved`
- `artifact.created`
- `finding.created`
- `report.created`
- `run.completed`
- `run.failed`

### 6.3 事件信封

所有 server -> client 事件统一采用 envelope：

- `conversation_id`
- `sequence`
- `event_kind`
- `timestamp`
- `session_id`
- `session_public_id`
- `payload`

### 6.4 reconnect 语义

v1 固定规则：

- 客户端断线不自动取消后台任务
- 客户端重连后通过 HTTP 获取当前 session/run 状态
- 之后重新建立 WebSocket 订阅
- 不要求回放所有历史事件，只要求：
  - 当前未决 approval
  - 当前 active run 状态
  - 最新 N 条 timeline event

## 7. Data and State Additions

需要在现有 session-centric 模型之上增加以下服务端状态对象。

### 7.1 OperatorConnection

作用：

- 表示桌面客户端与 App Server 的已认证连接

最小字段：

- `connection_id`
- `client_name`
- `connected_at`
- `last_seen_at`
- `auth_subject`

### 7.2 Conversation

作用：

- 服务端交互上下文
- 对应 `ConversationContext` 的服务化持有者

最小字段：

- `conversation_id`
- `connection_id`
- `active_session_id`
- `pending_clarification_id`
- `pending_approval_id`
- `updated_at`

### 7.3 ApprovalRequest

作用：

- 统一确认请求
- 支持 dashboard、审批中心、断线恢复

最小字段：

- `request_id`
- `session_id`
- `conversation_id`
- `action_name`
- `risk_level`
- `reason`
- `status`
- `created_at`
- `resolved_at`

### 7.4 Event Feed

作用：

- timeline、dashboard、run/job 详情的统一事实输入

要求：

- 所有关键动作写入事件
- query 层可按 session/run/job 聚合
- UI 不直接拼装运行时内部对象作为时间线来源

## 8. Detailed Implementation Phases

以下阶段顺序固定，不应调整。

## Phase A: App Server Foundation

### Goal

把当前 Python runtime 提升为可常驻运行的服务。

### Work Items

1. 新增 `src/server/app.py` 作为服务入口。
2. 选定并接入 `FastAPI`。
3. 新增 `src/server/lifecycle.py` 负责：
   - settings
   - service wiring
   - startup/shutdown hooks
4. 新增 `src/server/dependencies.py` 暴露：
   - `SessionService`
   - `SessionInteractionService`
   - `SessionRecordQueryService`
   - `ReportFlowService`
   - `DashboardService`
   - `ExecutionService`
5. 新增：
   - `GET /api/health`
   - `POST /api/connections`
6. 为本地/远程模式统一 server config。

### Modules to Add

- `src/server/app.py`
- `src/server/lifecycle.py`
- `src/server/dependencies.py`
- `src/server/routes/health.py`
- `src/server/routes/connections.py`

### Exit Criteria

- 服务可启动并常驻
- 能通过 HTTP 探活
- 能初始化所有核心 service
- 不依赖 CLI shell loop 才能运行

## Phase B: Conversation and Realtime Gateway

### Goal

把当前 Web adapter 提升为真正的 WebSocket 实时交互层。

### Work Items

1. 新增 `src/server/ws.py`。
2. 把 `src/web/interaction_adapter.py` 接到真实 WebSocket 连接。
3. 正式化 `conversation_id` 生命周期：
   - create
   - bind
   - reconnect
   - close
4. 扩展 `src/web/conversation_store.py`：
   - connection ownership
   - pending approval lookup
   - reconnect lookup
5. 新增 `connection_service.py` 管理 active connections。
6. 新增 `approval_service.py` 管理 pending approvals。
7. 固化 sequence ordering。
8. 统一 client/server 消息 envelope 与错误格式。

### Modules to Add or Extend

- `src/server/ws.py`
- `src/app/connection_service.py`
- `src/app/approval_service.py`
- `src/web/conversation_store.py`
- `src/web/interaction_adapter.py`

### Exit Criteria

- 桌面客户端可建立 WebSocket
- 一条 message 可驱动 controller + execution
- progress/clarification/confirmation 可通过 WebSocket 完整往返

## Phase C: Query and Dashboard API Completion

### Goal

补齐 GUI 大屏和详情页所需查询接口。

### Work Items

1. 新增 route groups：
   - `sessions.py`
   - `dashboard.py`
   - `reports.py`
   - `artifacts.py`
   - `approvals.py`
2. 对现有服务做 facade 封装，避免 route 直接操作底层对象。
3. 为 artifact/report 增加下载接口。
4. 为 dashboard 增加聚合 API：
   - active sessions
   - active runs/jobs
   - recent findings
   - recent reports
   - pending approvals
5. 为 timeline 增加事件列表 API。

### Modules to Add or Extend

- `src/server/routes/sessions.py`
- `src/server/routes/dashboard.py`
- `src/server/routes/reports.py`
- `src/server/routes/artifacts.py`
- `src/server/routes/approvals.py`
- `src/app/event_stream_service.py`

### Exit Criteria

- dashboard 页面无需 CLI 逻辑即可初始化
- findings/artifacts/reports 页面可全部通过 HTTP 加载
- session workspace 可通过 HTTP + WebSocket 混合驱动

## Phase D: Detached Execution and Job Control

### Goal

建立“客户端断开后后端继续执行”的后台执行主路径。

### Work Items

1. 定义 run lifecycle：
   - `queued`
   - `running`
   - `waiting_confirmation`
   - `paused`
   - `completed`
   - `failed`
   - `cancelled`
2. 明确 foreground 与 background 的入口差异。
3. 将现有 job/scheduler/runtime 接到 session-centric 主路径。
4. 增加：
   - `cancel_run`
   - `pause_run`（如当前实现成本高，可记录为 v1.1）
   - `resume_background_run`（同上）
5. 让后台任务统一写 event feed。
6. 让 reconnect 后能查询当前后台任务状态。

### Modules to Add or Extend

- `src/app/run_control_service.py`
- `src/app/event_stream_service.py`
- `src/orchestration/` 现有 job/scheduler 相关模块
- `src/runtime/` 现有 worker runtime 模块

### Exit Criteria

- 长时间任务不依赖桌面客户端持续在线
- 客户端可取消运行中的任务
- dashboard 能看到后台任务状态

## Phase E: Desktop Client Buildout

### Goal

完成独立桌面客户端工程。

### Fixed Tech

- `Tauri`
- `React`
- `TypeScript`
- `Vite`

### Work Items

1. 新建 `desktop-client/`。
2. 实现基础 app shell：
   - top bar
   - left navigation
   - workspace layout
3. 实现 connection manager：
   - local server profile
   - remote server profile
   - reconnect
4. 实现 API client：
   - typed HTTP wrapper
   - typed WebSocket wrapper
5. 实现状态层：
   - current connection
   - current conversation
   - current session
   - dashboard
   - approvals
   - timeline
6. 实现页面：
   - dashboard
   - session workspace
   - activity timeline
   - findings/artifacts
   - reports
   - approval center

### Recommended Internal Frontend Layout

- `src/app/`
- `src/features/dashboard/`
- `src/features/sessions/`
- `src/features/timeline/`
- `src/features/findings/`
- `src/features/artifacts/`
- `src/features/reports/`
- `src/features/approvals/`
- `src/features/connections/`
- `src/lib/api/`
- `src/lib/ws/`
- `src/lib/state/`
- `src/lib/types/`

### Exit Criteria

- 客户端可独立启动
- 可连接本地或远程 server
- 可在 GUI 中完成一条 session 交互
- 可实时看到 progress 和 approval

## Phase F: Productization and Operations

### Goal

把系统从“可运行 demo”变成“可部署产品”。

### Work Items

1. 增加最小认证壳：
   - local admin secret
   - remote bearer token
2. 增加审计日志：
   - operator connect/disconnect
   - approval decisions
   - report export
3. 增加部署脚本：
   - local start
   - remote start
4. 增加客户端打包：
   - macOS
   - Windows（如当前环境不做，文档中也要注明）
5. 增加恢复策略：
   - server restart 后 connection 失效
   - conversation 需要重建
   - session/run 状态需可重新查询
6. 完善运维文档。

### Exit Criteria

- 单用户可在本地模式完整使用
- 单用户可连接远程 server 使用
- 客户端和服务端具备可交付的启动、连接、断线恢复与日志能力

## 9. Detailed File and Module Recommendations

### 9.1 后端新增模块

- `src/server/app.py`
  - FastAPI app factory
- `src/server/dependencies.py`
  - 统一 service 装配
- `src/server/lifecycle.py`
  - startup/shutdown hooks
- `src/server/auth.py`
  - token 验证
- `src/server/ws.py`
  - WebSocket session gateway
- `src/server/routes/health.py`
- `src/server/routes/connections.py`
- `src/server/routes/sessions.py`
- `src/server/routes/reports.py`
- `src/server/routes/dashboard.py`
- `src/server/routes/approvals.py`
- `src/server/routes/artifacts.py`
- `src/app/connection_service.py`
- `src/app/conversation_service.py`
- `src/app/approval_service.py`
- `src/app/event_stream_service.py`
- `src/app/run_control_service.py`

### 9.2 需要重点改造的现有模块

- `src/web/interaction_adapter.py`
  - 从“适配层雏形”升级为真实 server-side conversation gateway
- `src/web/conversation_store.py`
  - 从简单内存存储升级为 connection-aware store
- `src/web/contracts.py`
  - 补全 connection/run/approval/event feed DTO
- `src/web/serialization.py`
  - 增加 dashboard/timeline/download metadata 相关 serialization
- `src/app/execution_service.py`
  - 与 detached/background control 更紧密集成
- `src/runtime/` 与 `src/orchestration/`
  - 对接 background 主路径

### 9.3 保持稳定复用的模块

- `src/app/session_interaction_service.py`
- `src/app/session_service.py`
- `src/app/session_record_query_service.py`
- `src/app/report_flow_service.py`
- `src/app/dashboard_service.py`
- `src/controller/`

## 10. Testing Strategy

### 10.1 后端服务测试

必须覆盖：

- app startup/shutdown
- health endpoint
- connection bootstrap
- WebSocket message round-trip
- clarification round-trip
- confirmation round-trip
- event ordering
- reconnect behavior

### 10.2 业务服务测试

必须覆盖：

- `SessionInteractionService` 仍能正确驱动 controller 与 execution
- `ExecutionService` 在 InteractionPort 下仍能发 progress 与确认
- dashboard、history、findings、reports 查询服务在 HTTP facade 下结果正确

### 10.3 后台执行测试

必须覆盖：

- detached/background run 启动
- 运行中取消
- 客户端断开后继续执行
- reconnect 后查询 run/job 状态

### 10.4 桌面客户端测试

必须覆盖：

- connection profile 保存
- WebSocket 重连
- timeline 实时刷新
- approval UI 响应
- reports/findings/artifacts 页面加载

## 11. Acceptance Criteria

改造完成的最小可接受标准：

1. 服务端可独立启动，不依赖 CLI shell。
2. 桌面客户端可连接本地或远程服务端。
3. 用户可从客户端创建或恢复 session。
4. foreground execution 可在客户端实时显示 progress。
5. confirmation-required 动作可在客户端批准或拒绝。
6. 后台任务在客户端断开后仍可继续运行。
7. reconnect 后可恢复查看当前 session 和最近运行状态。
8. dashboard、findings、artifacts、reports 页面可从服务端加载。
9. SQLite + 本地文件模式可支持完整单用户工作流。
10. 现有 CLI 在迁移期间仍可继续作为兼容入口。

## 12. Rollout Order

实施顺序固定为：

1. Phase A: App Server Foundation
2. Phase B: Conversation and Realtime Gateway
3. Phase C: Query and Dashboard API Completion
4. Phase D: Detached Execution and Job Control
5. Phase E: Desktop Client Buildout
6. Phase F: Productization and Operations

原因：

- 没有 App Server，就没有真正的独立客户端
- 没有实时网关，GUI 只是静态页面
- 没有查询 API，大屏和详情页无法成立
- 没有 detached execution，就达不到控制台产品形态
- 没有桌面客户端，产品体验仍停留在 CLI/接口测试阶段

## 13. Future Extension After v1

v1 完成后，后续可按以下方向扩展：

- 增加 browser Web client
  - 推荐使用 `Next.js + TypeScript`
  - 复用相同 HTTP/WebSocket 协议
- 增加 PostgreSQL 与 object storage
- 增加多用户与权限角色
- 增加多 worker 节点
- 增加更强的 dashboard analytics

这些扩展不应阻塞当前 v1 改造。
