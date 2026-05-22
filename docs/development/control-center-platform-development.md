# CTF Control Center Development Plan

## 1. Purpose

本文档定义 CTF 靶场 Agent 控制平台的工程实施计划。它对应：

- `docs/SPEC2.md`
- `docs/design/control-center-platform-design.md`
- `docs/architecture/control-center-target-architecture.zh.md`

目标是把产品和架构拆成可以逐步交付、测试和验收的开发阶段。

## 2. Development Principles

实施必须遵守：

- 先打通端到端闭环，再扩展扫描深度。
- 保持 Python Agent 和 runtime 为后端核心。
- 桌面端只做展示和操作，不承载业务事实。
- 扫描工具通过适配器接入，不在业务层拼 shell 字符串。
- 结构化结果和原始输出都必须保存。
- 攻击路径、证据和 writeup 必须来自持久化数据，不依赖聊天文本。
- 优先满足个人 CTF 靶场效率，不引入多用户和企业化复杂度。

## 3. Target Milestones

```text
Phase 0: Foundation alignment
Phase 1: App Server and Desktop Shell
Phase 2: Project / Session / Task Persistence
Phase 3: Scanner Adapter Layer
Phase 4: Realtime Agent Enumeration Loop
Phase 5: Attack Path and Evidence Workspace
Phase 6: External Command Result Capture
Phase 6.5: LLM Agent Orchestrator and Tool Router
Phase 7: Writeup Generation
Phase 8: Hardening and Packaging
```

每个阶段必须有可运行、可测试的结果。

## 4. Phase 0: Foundation Alignment

### 4.1 Goal

明确当前代码基线和新增模块边界，避免把 CTF 平台逻辑塞进旧 CLI 入口。

### 4.2 Implementation Tasks

- 确认现有 `src/app`, `src/web`, `src/storage`, `src/orchestration` 可复用服务。
- 确认现有 session、event、artifact、finding、report 模型与 CTF 新模型的重叠点。
- 新增或预留 CTF 专用服务命名：
  - `ProjectService`
  - `TargetSessionService`
  - `AttackPathService`
  - `ScannerService`
  - `WriteupService`
- 定义新增表的迁移方式。
- 定义 `.red-code/projects/` 文件目录规范。

### 4.3 Tests

- 现有测试必须继续通过。
- 新增空服务或模型时，必须增加最小 import 和 construction 测试。

### 4.4 Acceptance

- 新模块边界明确。
- 无运行时代码依赖 Tauri 或前端。
- CLI 入口未被改造成服务端入口。

## 5. Phase 1: App Server and Desktop Shell

### 5.1 Goal

建立常驻后端和桌面客户端壳，打通 HTTP 与 WebSocket。

### 5.2 Backend Tasks

新增：

- `src/server/app.py`
- `src/server/dependencies.py`
- `src/server/lifecycle.py`
- `src/server/ws.py`
- `src/server/routes/health.py`

实现：

- FastAPI app factory
- lifecycle 初始化
- health endpoint
- WebSocket connection 接入
- server-to-client event envelope
- development 启动命令

推荐运行命令：

```bash
.venv/bin/python -m uvicorn server.app:create_app --factory --reload
```

如果当前项目没有 `.venv`，开发者必须先按仓库规范创建虚拟环境。

### 5.3 Desktop Tasks

新增 `desktop-client/`：

- Tauri
- React
- TypeScript
- Vite
- API client
- WebSocket client
- App shell
- connection status

v1 桌面端首屏：

- Project list placeholder
- active connection indicator
- backend health check result
- WebSocket event log panel

### 5.4 Tests

Backend:

- `GET /api/health` returns ok.
- WebSocket accepts connection and emits connected event.
- App factory can be imported without side effects.

Frontend:

- TypeScript build passes.
- API client can parse health response.
- WebSocket client handles connect/disconnect.

### 5.5 Acceptance

- 用户可以启动后端。
- 用户可以启动 Tauri 桌面端。
- 桌面端显示后端连接状态。
- WebSocket 断开和重连有 UI 状态。

## 6. Phase 2: Project / Session / Task Persistence

### 6.1 Goal

完成 CTF 工作区核心数据模型，让 UI 可以创建和恢复 Project / Session。

### 6.2 Backend Tasks

新增模型和 repository：

- `Project`
- `TargetSession`
- `Task`
- `Event`
- `Evidence`
- `AttackPathNode`
- `Flag`

新增服务：

- `ProjectService`
- `TargetSessionService`
- `EventStreamService`

新增路由：

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/sessions`
- `POST /api/projects/{project_id}/sessions`
- `GET /api/sessions/{session_id}`
- `GET /api/sessions/{session_id}/dashboard`

补充要求：

- Session dashboard 需要完整填充目标摘要、开放端口、Web 入口、目录发现、POC 命中、攻击路径、下一步建议、最近命令、证据和 flag。
- `ws/events` 需要支持按 `session_id` / `project_id` 回放持久化事件，便于重连或后端重启后恢复历史事件。

实现文件布局：

```text
.red-code/projects/<project_id>/
.red-code/projects/<project_id>/sessions/<session_id>/
.red-code/projects/<project_id>/sessions/<session_id>/artifacts/
.red-code/projects/<project_id>/sessions/<session_id>/reports/
```

### 6.3 Desktop Tasks

实现：

- Project list
- Create Project dialog
- Project workspace route
- Create Target Session form
- Session sidebar
- Session dashboard placeholder

### 6.4 Tests

- Project create/list/get repository tests.
- Session create/list/get repository tests.
- Filesystem directory creation tests using temp dir.
- Dashboard empty state serialization test.
- Frontend form validation tests where practical.

### 6.5 Acceptance

- 用户可以创建 Project。
- 用户可以在 Project 中创建目标 Session。
- 重启后 Project 和 Session 仍可恢复。
- 空 Session dashboard 展示目标和空状态。

## 7. Phase 3: Scanner Adapter Layer

### 7.1 Goal

接入 `nmap`、`ffuf`、`nuclei`，形成结构化扫描任务。

### 7.2 Shared Scanner Tasks

新增：

- `src/scanners/contracts.py`
- `src/scanners/process_runner.py`
- `src/scanners/registry.py`
- `src/scanners/nmap_adapter.py`
- `src/scanners/ffuf_adapter.py`
- `src/scanners/nuclei_adapter.py`

统一实现：

- tool path resolution
- version check
- argv list construction
- working directory management
- stdout/stderr streaming
- timeout handling
- raw output file persistence
- structured parser result
- evidence candidate generation
- API task creation returns a queued task immediately; execution runs in the in-process scanner runtime
- cancellation marks queued/running tasks cancelled and running processes observe the cancellation probe

### 7.3 nmap Adapter

Required behavior:

- Accept target host and port options.
- Generate XML output.
- Parse open ports, protocol, service, product, version.
- Save XML and stdout.
- Generate service findings and attack path candidates.

Required tests:

- argv construction uses list, not shell string.
- XML fixture parses open ports correctly.
- missing binary returns diagnostic error.
- non-zero exit records stderr artifact.

### 7.4 ffuf Adapter

Required behavior:

- Accept base URL and wordlist.
- Generate JSON output.
- Parse status, length, words, lines, redirect location.
- Save JSON and stdout.
- Generate web path evidence.

Required tests:

- argv construction includes `FUZZ` safely.
- JSON fixture parses discovered paths.
- missing wordlist returns validation error.
- noise filters are preserved in task input.

### 7.5 nuclei Adapter

Required behavior:

- Accept target URL or host.
- Generate JSONL output.
- Parse template id, name, severity, matched URL, extracted results.
- Save JSONL and stdout.
- Generate POC findings and evidence.

Required tests:

- JSONL fixture parses multiple matches.
- severity and template metadata are preserved.
- empty result returns successful no finding state.
- missing templates produce actionable diagnostic.

### 7.6 Backend Routes

Add:

- `GET /api/tools/status`
- `GET /api/tools/config`
- `PATCH /api/tools/config`
- `POST /api/sessions/{session_id}/tasks`
- `GET /api/sessions/{session_id}/tasks`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/rerun`

### 7.7 Desktop Tasks

Implement:

- tool status panel
- scan task creation panel
- task queue list
- task detail drawer
- raw output link
- scan result tables

### 7.8 Acceptance

- 用户能在 UI 中看到 nmap/ffuf/nuclei 是否可用。
- 用户能手动启动端口扫描。
- 用户能手动启动目录扫描。
- 用户能手动启动 nuclei 验证。
- 每个扫描任务都有结构化结果和原始输出。

## 8. Phase 4: Realtime Agent Enumeration Loop

### 8.1 Goal

让 Agent 自动执行枚举闭环：端口扫描 -> Web 探测 -> 目录扫描 -> POC 验证建议。

### 8.2 Backend Tasks

新增：

- `CTFAgentService`
- `EnumerationPlanner`
- `EnumerationResultReducer`

Agent tools:

- `start_port_scan`
- `start_dir_scan`
- `start_poc_scan`
- `summarize_scan_result`
- `create_attack_path_node`
- `suggest_command`

Behavior:

- Chat 输入会创建当前 Session 作用域内的 `agent_analysis` 任务。
- 后端不通过手写关键词或正则对 Chat 输入做自然语言 intent 分类。
- 扫描、证据、攻击路径和报告动作由 LLM Agent 通过受控 tool call 选择。
- 如果缺少目标，Agent 请求用户创建或选择 Session。
- Agent 可创建 port scan、dir scan、nuclei scan 等 task。
- Agent 可根据工具结果生成下一步建议。
- 每一步通过 WebSocket 推送。

### 8.3 Desktop Tasks

Implement Agent Console:

- streaming response
- tool call cards
- task status cards
- next action cards
- error cards

### 8.4 Tests

- Agent service can build context from session state.
- Planner selects ffuf only for HTTP/HTTPS services.
- Planner does not start nuclei without candidate target.
- WebSocket event sequence remains ordered.
- Failed scan produces recoverable Agent summary.

### 8.5 Acceptance

- 用户在 Chat 中输入枚举请求后，系统能自动启动端口扫描。
- 扫描完成后自动生成服务摘要。
- 对 Web 服务自动生成目录扫描。
- Agent 生成下一步建议。
- UI 实时展示工具调用和任务结果。

### 8.6 Current Implementation Notes

当前 Phase 4 基线实现为本地确定性 Agent 编排，不依赖在线 LLM 调用：

- `POST /api/sessions/{session_id}/agent/messages` 接收 Agent Console 消息。
- `CTFAgentService` 创建 `agent_analysis` task，并在后台执行枚举工作流。
- `EnumerationPlanner` 仅对 HTTP/HTTPS 服务规划 ffuf，并且只有存在候选 URL 时才规划 nuclei。
- `EnumerationResultReducer` 将扫描 task 结果转换为 Agent 摘要；端口扫描失败会生成可恢复摘要和下一步建议。
- WebSocket 连接期间会轮询持久化事件，向 UI 推送 Agent、task 和 scanner 事件。
- 桌面端 Agent Console 展示工具调用、任务状态、下一步建议和错误类事件。

## 9. Phase 5: Attack Path and Evidence Workspace

### 9.1 Goal

将扫描、命令和分析结果组织为攻击路径。

### 9.2 Backend Tasks

Implement:

- `AttackPathService`
- evidence creation from task result
- finding creation from scanner result
- attack path node generation rules
- manual evidence creation
- flag creation

Routes:

- `GET /api/sessions/{session_id}/attack-path`
- `POST /api/sessions/{session_id}/attack-path`
- `GET /api/sessions/{session_id}/evidence`
- `POST /api/sessions/{session_id}/evidence`
- `GET /api/sessions/{session_id}/findings`
- `PATCH /api/findings/{finding_id}`
- `GET /api/sessions/{session_id}/flags`
- `POST /api/sessions/{session_id}/flags`

### 9.3 Desktop Tasks

Implement:

- attack path board
- node detail panel
- evidence list
- finding list
- flag/loot list
- manual note node
- link evidence to node

### 9.4 Node Generation Rules

Minimum rules:

- nmap open port -> service node
- HTTP service -> web entry node
- ffuf discovered path -> web enum node
- nuclei match -> poc verified node
- manual evidence -> note node
- flag record -> flag node

### 9.5 Tests

- nmap parsed result creates service nodes.
- ffuf result creates web enum nodes.
- nuclei result creates finding and POC node.
- manual evidence can link to node.
- flag can link to evidence.

### 9.6 Acceptance

- 用户能从 Session 看到攻击路径。
- 每个节点能展开查看来源证据。
- 用户能手动添加节点和证据。
- flag 能在攻击路径中展示。

### 9.7 Current Implementation Notes

当前 Phase 5 基线实现为本地持久化 workspace，不依赖在线 LLM 调用：

- `AttackPathService` 负责攻击路径、证据、finding、flag 的组合写入和读取。
- SQLite 新增 `ctf_findings` 与 `ctf_attack_path_evidence_links`，用于保存 CTF finding 和节点到证据的展开关系。
- 扫描成功后会继续保存结构化 evidence 和 attack path node，并根据扫描结果生成 finding：
  - `port_scan` 的 service evidence 生成信息级 finding。
  - `dir_scan` 的 web path evidence 生成信息级 finding。
  - `poc_scan` 的 nuclei 命中生成 verified finding，并保留 severity。
- 最小节点规则已接入：
  - nmap open port 生成服务枚举节点。
  - HTTP/HTTPS 服务额外生成 web enum 节点。
  - ffuf discovered path 生成 web enum 节点。
  - nuclei match 生成 verified POC 节点。
  - manual evidence 生成 note 节点。
  - flag/loot 生成 flag 节点。
- 新增 HTTP routes：
  - `GET /api/sessions/{session_id}/attack-path`
  - `POST /api/sessions/{session_id}/attack-path`
  - `GET /api/sessions/{session_id}/evidence`
  - `POST /api/sessions/{session_id}/evidence`
  - `GET /api/sessions/{session_id}/findings`
  - `PATCH /api/findings/{finding_id}`
  - `GET /api/sessions/{session_id}/flags`
  - `POST /api/sessions/{session_id}/flags`
- Session dashboard 会统计 finding severity，并继续展示证据、flag、攻击路径和下一步建议。
- 桌面端增加 Attack Path、Evidence、Findings、Flags/Loot 的 workspace 面板，并提供手动 note/evidence 节点入口。

## 10. Phase 6: External Command Result Capture

### 10.1 Goal

v1 不提供内置交互终端。Phase 6 的目标是把用户在系统外部执行得到的命令结果、文件和笔记整理进 evidence 流，而不是在产品内承载命令执行。

### 10.2 Backend Tasks

新增或明确：

- 外部命令结果 evidence 约定
- 命令建议事件格式
- 外部结果导入到 attack path / finding / writeup 的关联规则

Behavior:

- Agent 只生成命令建议，不在产品内执行命令。
- 用户在外部工具环境中执行命令。
- 用户可以把命令文本、结果摘录、文件、截图或原始输出整理为 evidence。
- 这些材料可关联到 attack path node、finding 和 writeup。

### 10.3 Desktop Tasks

Implement:

- command suggestion cards
- external result intake form
- evidence attachment flow for files / screenshots / pasted output

### 10.4 Tests

- 外部命令结果 evidence payload 校验通过。
- 命令结果 evidence 能关联到 attack path 或 finding。
- 上传或粘贴的外部结果能够持久化并恢复。

### 10.5 Acceptance

- 用户能看到 Agent 给出的命令建议。
- 用户能把外部命令结果整理为 evidence。
- evidence 能进入 attack path 和 writeup 工作流。


## 10.5. Phase 6.5: LLM Agent Orchestrator and Tool Router

### 10.5.1 Goal

将当前确定性的 Phase 4 Agent 编排升级为真实 LLM Agent 主路径。Agent 应能理解普通用户输入、读取当前 Project/Session 上下文，并通过受控高层工具创建扫描、证据、攻击路径、finding、命令建议和 writeup 草稿。

### 10.5.2 Backend Tasks

新增：

- `AgentOrchestrator`
- `AgentToolRouter`
- Control Center Agent tool schemas

Agent tools:

- `start_port_scan`
- `start_dir_scan`
- `start_poc_scan`
- `summarize_task_result`
- `create_attack_path_node`
- `create_finding`
- `suggest_command`
- `create_writeup_draft`

Behavior:

- 普通问答交由 LLM 回答，不再落入固定枚举 fallback。
- 扫描类请求由 LLM 选择高层 tool call。
- tool call 参数必须经过 schema 校验和 Session scope 校验。
- Agent 不获得原始 `bash` 或任意 shell 字符串执行能力。
- 命令只作为建议写入事件，由用户在系统外部明确执行。
- 不保留基于自然语言关键词的确定性枚举 fallback；自由文本只交给 LLM 处理。

### 10.5.3 Desktop Tasks

Extend Agent Console:

- render `conversation.delta`
- render `conversation.completed`
- render `agent.tool_call.started`
- render `agent.tool_call.completed`

### 10.5.4 Tests

- 普通问答不会返回 Phase 4 固定 fallback。
- 枚举/侦察类请求能通过 tool call 创建扫描任务。
- 未注册 tool call 被拒绝并记录错误事件。
- 越界扫描目标被拒绝。
- WebSocket 能推送 conversation 与 tool call 事件。

### 10.5.5 Acceptance

- 用户问“你是什么模型”时，Agent 返回真实文本响应。
- 用户要求枚举目标时，Agent 能通过高层工具创建扫描任务。
- 所有 tool call 都有结构化事件并可在前端展示。
- 现有 Phase 4/5/6 回归测试继续通过。

## 11. Phase 7: Writeup Generation

### 11.1 Goal

从结构化数据生成 Markdown writeup 草稿。

### 11.2 Backend Tasks

新增：

- `WriteupService`
- 两段式 LLM 生成流程：主 Agent 汇总结构化资料，辅助报告 Agent 生成 Markdown
- Control Center 专用 `ctf_reports` 持久化，不复用 legacy Report
- report material 与 writeup 文件按 report public id 版本化保存在 Project/Session 报告目录
- 生成后校验必需章节、未知 public id、事实性条目 public id 引用和 Command Log 命令来源
- Command Log 命令来源包含用户明确录入到 evidence/notes 的命令文本与 Scanner Task 的 `argv`

Routes:

- `GET /api/sessions/{session_id}/reports`
- `POST /api/sessions/{session_id}/reports`
- `GET /api/projects/{project_id}/reports`
- `POST /api/projects/{project_id}/reports`
- `GET /api/reports/{report_id}/download`

Writeup sections:

- Overview
- Target
- Recon
- Open Ports
- Web Enumeration
- Vulnerability Hypotheses
- Verification
- Exploit Notes
- Privilege Escalation Notes
- Flags and Loot
- Command Log
- Evidence Index
- TODO

### 11.3 Desktop Tasks

Implement:

- writeup preview
- generate button
- regenerate button
- open file action with Tauri report-path guard restricted to generated `writeup.md`
- evidence/finding/task/command public id reference navigation

### 11.4 Tests

- empty session writeup has useful skeleton.
- populated session writeup includes ports, paths, findings, commands, flags.
- generated Markdown references evidence ids.
- validator rejects unknown public ids, unrecorded commands, and uncited factual lines.
- Scanner Task `argv` commands are accepted as recorded command sources.

### 11.5 Acceptance

- 用户能生成 Session writeup。
- Writeup 包含扫描、命令、证据和 flag。
- Writeup 文件保存在 Project 目录。
- UI 可以预览或打开 writeup。

## 12. Phase 8: Hardening and Packaging

### 12.1 Goal

提高稳定性、跨平台可用性、部署清晰度和开发体验。Phase 8 的 packaged desktop app
必须明确采用 client/server 连接模型：桌面端是客户端，Python App Server 是后端执行环境。
本阶段可以支持本机 all-in-one 体验，但不应把 UI 和后端业务逻辑合并成一个不可拆分的进程。

### 12.2 Tasks

- Tool installation diagnostics
- configurable tool paths
- configurable wordlist paths
- configurable nuclei templates path
- task timeout settings
- process cancellation hardening
- WebSocket reconnect and event replay
- frontend error boundaries
- backend structured logging
- Tauri packaging
- runtime backend URL configuration for packaged desktop app
- local backend discovery or explicit local backend connection flow
- documented remote backend connection flow using a runtime backend URL
- optional single-user local auth config at `.red-code/config/control-center-auth.json`
- optional unified launcher command design for `server`, `client`, and `desktop` modes
- README update
- docs examples update

### 12.2.1 Packaged Connection Model

Supported modes:

- Local server mode: packaged desktop app connects to an already running local App Server at
  `http://127.0.0.1:<port>`.
- Remote server mode: packaged desktop app connects to a server-hosted App Server through the
  configured backend URL; the WebSocket URL is derived from that same backend URL.
- Local all-in-one mode: a launcher may start or discover the local App Server and then open the
  desktop client, while keeping the server and client as separate processes.

Required behavior:

- The client must be able to store or receive a backend URL at runtime; packaged builds must not
  depend only on build-time `VITE_BACKEND_URL`.
- The WebSocket URL must continue to derive from the selected backend URL so HTTP and event replay
  stay scoped to the same server.
- Remote server mode must treat the server as the source of truth for runtime state, artifacts,
  report files, tool paths, wordlists, templates, and evidence storage.
- Opening local report paths from Tauri is only valid for local server mode. Remote mode must use
  download or preview APIs instead of assuming the report exists on the client filesystem.

Recommended launcher shape:

```bash
red-code server --host 127.0.0.1 --port 8000
red-code server --host 0.0.0.0 --port 8000 --config ./server.toml
red-code client --backend-url http://red-agent.example.com:8000
red-code desktop
```

Connection baseline:

- App Server defaults to `127.0.0.1`.
- Binding to `0.0.0.0` is an explicit operator choice.
- Remote server mode is single-user in v1; multi-user isolation remains out of scope.

Optional Phase 8 auth config:

```json
{
  "enabled": true,
  "username": "admin",
  "password": "change-me"
}
```

If the auth config is missing or disabled, development remains unauthenticated. When enabled,
all HTTP APIs except `/api/health`, `/api/auth/session`, and `/api/auth/login` require
`Authorization: Bearer <token>`. `/ws/events` requires the same in-memory token through
`auth_token=<token>`.

### 12.3 Tests

- tool missing diagnostics
- task cancellation
- WebSocket reconnect
- event replay after reconnect
- Windows path serialization where possible
- frontend production build
- packaged app backend URL override or runtime configuration
- WebSocket URL derivation from configured backend URL
- local mode report opening behavior remains constrained to generated reports
- remote mode report access uses HTTP download or preview flow
- server command defaults to localhost binding
- backend full pytest suite
- frontend API tests for runtime backend URL, tool config, and API error messages
- Tauri `cargo check` and packaging smoke where platform dependencies are available

### 12.4 Acceptance

- Fresh checkout can run documented dev commands.
- Missing external tools are reported clearly.
- Packaged desktop app can connect to a local backend.
- Packaged desktop app can be configured to connect to a remote backend.
- Local all-in-one launcher can start or discover a local backend without weakening the client/server boundary.
- Remote backend deployment is documented as a client/server connection mode using the configured backend URL.
- Long-running scan can be canceled.
- UI can recover after WebSocket reconnect.

## 13. Required External Tools

v1 default tools:

- `nmap`
- `ffuf`
- `nuclei`

Optional but recommended later:

- `httpx`
- `feroxbuster`
- `rustscan`
- `whatweb`
- `gobuster`
- `curl`

Tool configuration must support:

- binary path override
- version detection
- default options
- wordlist paths
- nuclei templates path

## 14. Development Commands

Python commands must use the project virtual environment:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_scanner_adapters.py
.venv/bin/python -m uvicorn server.app:create_app --factory --reload
```

Frontend commands should run from `desktop-client/`:

```bash
npm install
npm run dev
npm run build
npm run tauri dev
npm run tauri -- build
```

Exact package manager can be chosen when the desktop client is created, but it must be documented in `README.md`.

## 15. Testing Strategy

### 15.1 Unit Tests

Required unit coverage:

- scanner argv construction
- scanner parser fixtures
- repository CRUD
- service state transitions
- event serialization
- writeup rendering
- attack path node generation

### 15.2 Integration Tests

Required integration coverage:

- Project -> Session -> Task creation
- scanner task lifecycle using fixture runners
- WebSocket event sequence
- evidence linking
- writeup generation from fixture Project

External tools should be mocked or replaced with fixture process runners in CI-style tests. Manual smoke tests can use real `nmap`, `ffuf`, and `nuclei`.

### 15.3 Manual Smoke Tests

Manual v1 smoke target:

1. Start backend.
2. Start desktop client.
3. Create Project.
4. Add target Session for a local or lab IP.
5. Run nmap scan.
6. Run ffuf against discovered HTTP service.
7. Run nuclei against candidate URL.
8. Record a manual note or external command result as evidence.
9. Record a flag.
10. Generate writeup.
11. Restart app and verify state recovery.

## 16. Documentation Updates

When behavior changes, update:

- `README.md`
- `docs/SPEC2.md` if product behavior changes
- `docs/design/control-center-platform-design.md` if architecture or contracts change
- `docs/development/control-center-platform-development.md` if phase scope or commands change

Examples must not omit setup details, required external tools, or expected output locations.

## 17. Definition of Done

A phase is done only when:

- code is implemented
- tests are added or explicitly justified
- docs are updated
- manual acceptance scenario passes where applicable
- no unrelated refactor is mixed into the phase
- generated artifacts are not accidentally committed unless intended

v1 is done only when the complete path works:

```text
Project -> Target Session -> Agent enumeration -> nmap -> ffuf -> nuclei
-> attack path -> manual evidence -> flag -> Markdown writeup -> recovery after restart
```
