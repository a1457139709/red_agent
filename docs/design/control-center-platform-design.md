# CTF Control Center Platform Design

## 1. Purpose

本文档定义 `red-code` 面向 CTF 靶场控制平台的目标设计。它基于现有 Python Agent 与 control-center 架构方向，但产品目标收敛为个人 CTF 靶场高效率工作台。

本文档回答：

- 系统由哪些子系统组成
- UI、API、Agent、扫描器、终端和存储如何协作
- Project、Session、Task、Evidence、Attack Path 如何建模
- `nmap`、`ffuf`、`nuclei` 如何通过统一执行层接入
- 实时事件和报告如何从运行时流向桌面端

## 2. Top-Level Architecture

```mermaid
graph TD
    Operator[Operator]
    Desktop[Tauri Desktop Client\nReact + TypeScript]
    API[App Server\nPython + FastAPI]
    WS[WebSocket Gateway]
    Agent[Agent Orchestrator\nLangChain]
    Runtime[Task Runtime\nScheduler + Workers]
    Scanner[Scanner Adapter Layer\nnmap / ffuf / nuclei]
    Terminal[Terminal Runtime\nPTY Sessions]
    DB[(SQLite)]
    Files[Filesystem Artifacts\noutputs / screenshots / scripts / writeups]

    Operator --> Desktop
    Desktop -->|HTTP| API
    Desktop -->|WebSocket| WS
    API --> Agent
    WS --> Agent
    Agent --> Runtime
    Runtime --> Scanner
    Runtime --> Terminal
    Runtime --> DB
    Scanner --> Files
    Terminal --> Files
    API --> DB
    API --> Files
```

核心原则：

- 桌面端负责交互、展示、连接、终端视图和本地用户体验。
- 后端负责业务状态、Agent 编排、任务调度、工具调用和持久化。
- Agent 不直接执行 shell 字符串扫描，必须通过 Scanner Adapter 或 Terminal Runtime。
- Scanner Adapter 输出结构化结果，同时保存原始输出。
- Terminal Runtime 面向用户交互命令，不替代结构化扫描执行层。
- SQLite 是 v1 结构化事实来源，文件系统保存大对象和原始材料。

## 3. Repository Shape

推荐目标目录：

```text
src/
  server/
    app.py
    dependencies.py
    lifecycle.py
    ws.py
    routes/
      health.py
      projects.py
      sessions.py
      tasks.py
      evidence.py
      findings.py
      reports.py
      terminal.py
  app/
    project_service.py
    target_session_service.py
    attack_path_service.py
    scanner_service.py
    terminal_service.py
    ctf_agent_service.py
    writeup_service.py
  scanners/
    contracts.py
    registry.py
    nmap_adapter.py
    ffuf_adapter.py
    nuclei_adapter.py
    process_runner.py
    parsers/
  terminal/
    pty_manager.py
    command_log.py
  storage/
    repositories/
  web/
    contracts.py
    serialization.py

desktop-client/
  src/
    app/
    features/
      projects/
      workspace/
      agent-console/
      attack-path/
      scans/
      terminal/
      evidence/
      writeup/
      settings/
    lib/
      api/
      ws/
      state/
      types/
  src-tauri/
```

Existing modules under `src/app`, `src/web`, `src/storage`, and `src/orchestration` should be reused where they fit, but new CTF-specific concepts should not be forced into legacy task/operation names.

## 4. Domain Model

### 4.1 Relationship Overview

```mermaid
classDiagram
    class Project {
      project_id
      name
      description
      root_path
      status
      created_at
      updated_at
    }

    class TargetSession {
      session_id
      project_id
      name
      target_value
      target_type
      status
      summary
      created_at
      updated_at
    }

    class Task {
      task_id
      project_id
      session_id
      task_type
      executor
      status
      input_json
      result_json
      started_at
      ended_at
    }

    class Event {
      event_id
      project_id
      session_id
      task_id
      event_kind
      level
      payload_json
      sequence
      created_at
    }

    class Evidence {
      evidence_id
      project_id
      session_id
      source_task_id
      evidence_type
      title
      summary
      content_ref
      payload_json
      created_at
    }

    class Finding {
      finding_id
      project_id
      session_id
      severity
      status
      title
      description
      evidence_refs
      created_at
    }

    class AttackPathNode {
      node_id
      project_id
      session_id
      stage
      title
      status
      source_ref
      next_action
      created_at
    }

    class CommandRun {
      command_run_id
      project_id
      session_id
      terminal_id
      command
      exit_code
      output_ref
      tags
      created_at
    }

    class Flag {
      flag_id
      project_id
      session_id
      flag_type
      value
      source_evidence_id
      created_at
    }

    class Report {
      report_id
      project_id
      session_id
      report_type
      file_ref
      created_at
    }

    Project --> TargetSession
    TargetSession --> Task
    Task --> Event
    Task --> Evidence
    Evidence --> Finding
    Evidence --> AttackPathNode
    TargetSession --> CommandRun
    TargetSession --> Flag
    Project --> Report
```

### 4.2 Entity Responsibilities

- `Project`
  - 顶层靶场容器
  - 管理多个目标 Session
  - 拥有 Project 级文件目录和 writeup
- `TargetSession`
  - 单台靶机或单个目标上下文
  - 绑定 target scope、攻击路径、任务和证据
- `Task`
  - 所有自动扫描、Agent 分析、终端命令记录和报告生成的执行事实
  - 不承载 UI 临时状态
- `Event`
  - 实时 UI、审计、恢复和时间线的统一事实
- `Evidence`
  - 结构化结果和原始材料之间的索引
  - 每条 evidence 必须可追溯到任务或用户手动输入
- `Finding`
  - 已整理的线索、漏洞假设或验证结论
- `AttackPathNode`
  - 攻击路径视图的基本单位
  - 可以来自 Task、Evidence、Finding、Flag 或用户手动创建
- `CommandRun`
  - 终端命令执行记录
  - 保存完整输出引用和摘要
- `Flag`
  - CTF 成果记录
  - 值可以选择遮蔽显示，但本地存储保留原文
- `Report`
  - Markdown writeup 或结构化导出文件索引

## 5. Desktop Client Design

### 5.1 Information Architecture

```mermaid
graph TD
    Shell[App Shell]
    Projects[Project List]
    Workspace[Project Workspace]
    Agent[Agent Console]
    Path[Attack Path]
    Scans[Scan Tasks]
    Terminal[Terminal]
    Evidence[Evidence and Findings]
    Writeup[Writeup]
    Settings[Settings]

    Shell --> Projects
    Shell --> Workspace
    Workspace --> Agent
    Workspace --> Path
    Workspace --> Scans
    Workspace --> Terminal
    Workspace --> Evidence
    Workspace --> Writeup
    Shell --> Settings
```

### 5.2 Workspace Layout

主工作区采用三栏结构：

- 左侧：Project / Session 导航、目标摘要、任务队列
- 中间：Agent Chat、实时工具调用、扫描进度、终端切换
- 右侧：攻击路径、证据、flag、下一步建议、writeup 摘要

设计要求：

- 扫描任务必须可见，不隐藏在聊天文本中。
- Agent 工具调用必须有结构化卡片。
- 攻击路径节点必须能展开查看证据。
- 终端输出必须可标记为 evidence。
- UI 必须支持在 Project、Session 和 Task 之间快速跳转。

### 5.3 Client State

客户端本地状态只保存：

- 当前连接配置
- 最近打开 Project
- 当前选中 Session
- UI 面板布局
- WebSocket 连接状态
- 未提交输入内容

业务事实必须以后端和 SQLite 为准。

## 6. App Server Design

### 6.1 Responsibilities

App Server 负责：

- HTTP API
- WebSocket Gateway
- Project / Session 服务组合
- Agent 消息路由
- Task 调度
- Scanner Adapter 调用
- Terminal Runtime 管理
- Evidence / Finding / Attack Path 生成
- Writeup 生成
- Artifact 下载

App Server 不负责：

- 在路由层直接实现扫描解析
- 绕过 service 层直接写复杂业务状态
- 让客户端决定任务终态

### 6.2 HTTP API Families

v1 HTTP 接口族：

```text
GET    /api/health

GET    /api/projects
POST   /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}

GET    /api/projects/{project_id}/sessions
POST   /api/projects/{project_id}/sessions
GET    /api/sessions/{session_id}
PATCH  /api/sessions/{session_id}

GET    /api/sessions/{session_id}/dashboard
GET    /api/sessions/{session_id}/attack-path
POST   /api/sessions/{session_id}/attack-path

GET    /api/sessions/{session_id}/tasks
POST   /api/sessions/{session_id}/tasks
POST   /api/tasks/{task_id}/cancel
POST   /api/tasks/{task_id}/rerun

GET    /api/sessions/{session_id}/evidence
POST   /api/sessions/{session_id}/evidence
GET    /api/evidence/{evidence_id}

GET    /api/sessions/{session_id}/findings
PATCH  /api/findings/{finding_id}

GET    /api/sessions/{session_id}/flags
POST   /api/sessions/{session_id}/flags

GET    /api/sessions/{session_id}/reports
POST   /api/sessions/{session_id}/reports
GET    /api/reports/{report_id}/download

GET    /api/tools/status
GET    /api/tools/config
PATCH  /api/tools/config

POST   /api/sessions/{session_id}/terminals
GET    /api/terminals/{terminal_id}/commands
POST   /api/commands/{command_run_id}/evidence
```

### 6.3 WebSocket Message Families

WebSocket 负责实时交互和实时事件。

Client to Server:

```text
conversation.message
conversation.cancel
session.bind
session.unbind
task.start
task.cancel
terminal.open
terminal.input
terminal.resize
terminal.close
evidence.create_from_selection
```

Server to Client:

```text
conversation.delta
conversation.completed
agent.tool_call.started
agent.tool_call.completed
task.queued
task.started
task.progress
task.completed
task.failed
scanner.output
terminal.output
terminal.exited
evidence.created
finding.created
attack_path.node_created
attack_path.node_updated
flag.created
report.created
error
```

Every server event must include:

- `event_id`
- `project_id`
- `session_id`
- `task_id` when available
- `sequence`
- `event_kind`
- `timestamp`
- `payload`

## 7. Agent Orchestrator Design

### 7.1 Responsibilities

Agent Orchestrator 负责：

- 理解用户输入
- 读取当前 Project / Session / Attack Path 上下文
- 制定枚举计划
- 调用任务服务创建扫描任务
- 分析扫描结果
- 生成 finding 和下一步建议
- 生成终端命令建议
- 生成 writeup 草稿

### 7.2 Agent Context

每次 Agent turn 至少包含：

- 当前 Project 摘要
- 当前 Session 目标
- 最近事件
- 开放端口摘要
- Web 资产摘要
- POC 命中摘要
- 攻击路径当前节点
- 最近命令摘要
- 已记录 flag/loot
- 可用工具和限制

### 7.3 Agent Tool Surface

Agent 可调用的高层工具：

- `create_project`
- `create_target_session`
- `start_port_scan`
- `start_dir_scan`
- `start_poc_scan`
- `summarize_task_result`
- `create_attack_path_node`
- `create_finding`
- `suggest_terminal_command`
- `create_writeup_draft`

Agent 不直接调用：

- 原始 `bash`
- 任意 shell 字符串扫描
- 未注册外部工具

终端命令由 Agent 建议，用户通过终端执行。

## 8. Scanner Adapter Design

### 8.1 Contract

统一扫描器接口：

```text
ScannerRequest
  request_id
  project_id
  session_id
  scanner_name
  target
  options
  output_dir

ScannerResult
  request_id
  scanner_name
  status
  summary
  findings
  evidence
  raw_output_refs
  started_at
  ended_at
  error
```

Adapter 必须：

- 校验目标属于 Session
- 构造安全参数列表
- 启动外部进程
- 流式读取 stdout/stderr
- 保存原始输出
- 解析结构化结果
- 生成 evidence candidates
- 返回明确错误

Adapter 不允许：

- 拼接未转义 shell 字符串
- 把 stdout 当作唯一结果
- 失败时吞掉原始输出

### 8.2 nmap Adapter

职责：

- 执行端口扫描和服务识别
- 默认生成 XML 输出
- 解析开放端口、协议、服务、版本、脚本输出

推荐命令形态：

```text
nmap -sV -oX <xml_output> <target>
```

可配置选项：

- port range
- scan timing
- service detection
- scripts
- retries
- timeout

输出：

- open ports
- service fingerprints
- host status
- evidence: raw XML、stdout、解析 JSON

### 8.3 ffuf Adapter

职责：

- 对 HTTP/HTTPS 目标执行目录和路径发现
- 使用 JSON 输出
- 过滤噪声状态码和响应大小

推荐命令形态：

```text
ffuf -u <base_url>/FUZZ -w <wordlist> -of json -o <json_output>
```

可配置选项：

- wordlist
- extensions
- status filters
- size filters
- rate
- recursion
- headers

输出：

- discovered paths
- status code
- response size
- redirect location
- content words/lines
- evidence: raw JSON、stdout、解析 JSON

### 8.4 nuclei Adapter

职责：

- 对候选 URL 或服务执行模板验证
- 保存 JSONL 输出
- 将命中结果转为 finding 和 evidence

推荐命令形态：

```text
nuclei -target <target> -jsonl -o <jsonl_output>
```

可配置选项：

- templates
- tags
- severity
- rate limit
- interactsh enabled/disabled
- headers

输出：

- template id
- name
- severity
- matched URL
- extracted results
- curl command when available
- evidence: raw JSONL、stdout、解析 JSON

## 9. Terminal Runtime Design

### 9.1 Responsibilities

Terminal Runtime 负责：

- 创建 PTY session
- 接收用户输入
- 流式返回输出
- 处理 resize
- 记录命令边界
- 保存输出 artifact
- 生成 CommandRun
- 支持输出片段转 evidence

### 9.2 Command Recording

命令记录必须包含：

- command text
- working directory
- environment summary
- started_at
- ended_at
- exit_code when available
- output artifact ref
- tags
- linked attack path node

交互命令可能没有清晰退出码。系统应允许用户手动结束记录并保存片段。

## 10. Persistence Design

### 10.1 SQLite

SQLite 保存：

- projects
- target_sessions
- tasks
- events
- evidence
- findings
- attack_path_nodes
- command_runs
- flags
- reports
- tool_configs

所有表必须包含：

- stable primary key
- created_at
- updated_at where mutable
- project_id where applicable
- session_id where applicable

### 10.2 Filesystem

文件布局建议：

```text
.red-code/
  projects/
    <project_id>/
      project.json
      sessions/
        <session_id>/
          artifacts/
            scans/
            terminal/
            evidence/
          reports/
            writeup.md
          scripts/
          notes/
      reports/
```

文件系统保存：

- nmap XML
- ffuf JSON
- nuclei JSONL
- stdout/stderr
- terminal output
- screenshots
- user-uploaded files
- generated scripts
- Markdown writeups

SQLite 中保存文件引用和摘要。

## 11. Attack Path Generation

攻击路径生成规则：

- nmap 开放端口生成 service 节点。
- HTTP/HTTPS 服务生成 web-entry 节点。
- ffuf 发现的重要路径生成 web-enum 节点。
- nuclei 命中生成 poc-verified 节点。
- 用户保存命令输出可生成 manual-evidence 节点。
- flag 记录生成 flag 节点。
- Agent 分析可以生成 hypothesis 和 next-action 节点。

节点状态：

- `new`
- `investigating`
- `verified`
- `dismissed`
- `blocked`
- `done`

节点必须可追溯到 source ref。

## 12. Writeup Generation

Writeup Service 从结构化数据生成 Markdown。

输入：

- Project metadata
- Session metadata
- Attack path nodes
- Evidence summaries
- Findings
- Command runs
- Flags

输出：

- Session writeup
- Project writeup

生成规则：

- 不编造未记录步骤。
- 命令必须来自 CommandRun 或 Scanner Task。
- 证据必须带引用。
- 未完成事项写入 TODO。
- flag 默认保留原值，后续可增加遮蔽选项。

## 13. Error Handling

必须明确处理：

- 外部工具不存在
- 外部工具版本不兼容
- wordlist 不存在
- 模板目录不存在
- 扫描进程超时
- 扫描进程非零退出
- 输出文件缺失或不可解析
- WebSocket 断开
- 客户端重连
- 终端进程退出

错误必须同时：

- 返回给 UI
- 记录 Event
- 保留可诊断原始输出

## 14. Security Boundary

v1 安全边界为轻量防误操作：

- Project / Session 声明目标范围。
- Scanner Adapter 只接受结构化参数。
- 执行外部工具时使用 argv list，不使用 shell 拼接。
- Agent 不直接获得任意 shell 执行工具。
- 终端命令由用户主动输入或明确触发。
- 危险命令在 UI 中标识。
- 所有扫描和命令执行都可追溯。

不设计：

- 多用户权限
- 企业审批
- 强制授权证明
- 远程多租户隔离

## 15. Cross-Platform Notes

目标支持 macOS、Linux、Windows。

必须注意：

- 外部工具路径可配置。
- PTY 实现按平台适配。
- 文件路径使用跨平台 API。
- 默认 wordlist 路径不能写死为 Linux 专用路径。
- Tauri shell 权限最小化配置。
- Windows 下终端 shell、换行和编码需要单独测试。

## 16. Acceptance Criteria

设计落地后，系统必须能完成：

1. 创建 Project 和 Target Session。
2. 通过 Agent Chat 发起自动枚举。
3. 后端调用 nmap、ffuf、nuclei 并产生结构化结果。
4. WebSocket 实时推送任务状态和工具输出。
5. 攻击路径自动出现服务、Web、POC 和 flag 节点。
6. 内置终端执行命令并保存输出。
7. 用户把终端输出保存为 evidence。
8. 生成 Markdown writeup。
9. 重启客户端后恢复 Project 状态。
10. 外部工具缺失时展示明确错误。
