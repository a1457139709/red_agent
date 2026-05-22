# SPEC2: CTF 靶场 Agent 控制平台需求分析

## 1. 背景

`red-code` 当前已经具备本地 Python Agent、session 持久化、SQLite 存储、基础红队工具、Web DTO 与运行时事件雏形。下一阶段目标不是简单给 CLI 增加图形界面，而是把现有能力演进为面向 CTF 靶场的高效率攻防 Agent 控制平台。

本文档定义产品级需求，作为后续设计文档和开发文档的上游依据。

## 2. 产品定位

目标产品是：

- 面向个人安全从业者的 CTF/靶场桌面控制平台
- 以 Agent 为核心的枚举、分析、行动建议和复盘助手
- 以 Project 管理靶场，以 Session 承载 Agent 对话与执行上下文
- 以 Project Target Pool 管理靶机、URL、域名、主机和目标准入状态
- 以攻击路径视图组织资产、服务、线索、证据、命令、flag 和报告
- 本地优先、单用户、单节点、可恢复、可复盘

目标产品不是：

- 企业级多用户攻防平台
- 商业化漏洞管理系统
- 默认全自动攻击框架
- 只展示扫描结果的 Web UI
- 纯命令行工具包装器

## 3. 用户与场景

### 3.1 主要用户

主要用户是熟悉安全测试、CTF 靶机、Linux 命令、Web 漏洞和常见扫描工具的个人安全从业者。

用户假设：

- 用户自行控制授权和靶场范围
- 用户希望提升枚举、整理、复盘和报告效率
- 用户能够判断 exploit、弱口令、写文件、反连 shell 等动作的风险
- 用户需要透明看到 Agent 做了什么、发现了什么、为什么建议下一步

### 3.2 主要场景

系统优先支持综合靶机场景，例如 HackTheBox、VulnHub、本地靶场、内网实验靶场。

典型流程：

1. 创建 CTF Project，例如 `HTB-Lab`。
2. 在 Project 中添加目标 Session，例如 `10.10.10.5`。
3. Agent 自动执行基础枚举，识别端口、服务和 Web 入口。
4. 系统根据结果生成攻击路径节点和下一步建议。
5. 用户在外部工具环境中执行 Agent 给出的命令建议或自行选择的验证步骤，验证漏洞或尝试利用。
6. 命令输出、响应包、截图、payload、flag 被归档为证据。
7. Agent 根据证据更新攻击路径和 writeup 草稿。
8. 用户随时恢复 Project，查看历史、复跑命令、继续攻击或生成复盘。

## 4. 产品目标

### 4.1 v1 目标

v1 必须完成一个端到端控制闭环：

- 桌面 UI 可以创建和恢复 Project / Session
- UI 可以通过 WebSocket 与后端实时交互
- Agent 可以理解 CTF 目标并驱动枚举工作流
- 扫描执行层可以调用独立工具执行端口扫描、目录扫描和 POC 验证
- 扫描结果可以持久化并进入攻击路径
- 用户可以把命令输出、工具结果、flag、文件记录为证据
- 系统可以生成 Markdown Writeup 草稿

### 4.2 非目标

v1 不做：

- 多用户、租户、RBAC、组织空间
- 企业审计、合规审批、工单流
- 分布式 worker 集群
- 云端托管平台
- 默认自动 exploit 或自动提权
- 大规模互联网扫描
- 对旧实现做长期兼容妥协

## 5. 核心概念

### 5.1 Project

Project 是顶层靶场工作区。

Project 用于组织：

- 多个目标 Session
- Project 级笔记
- Project 级字典、payload、模板和报告
- Project 总览 dashboard
- Project 级 writeup 或复盘目录

示例：

- `HTB-Offshore`
- `VulnHub-OSCP-Practice`
- `Local-AD-Lab`

### 5.2 Session 与 Target Pool

Session 表示 Project 中一个 Agent 对话与执行上下文，不绑定单个目标。

一个 Session 负责承载：

- Agent 对话历史
- 扫描任务和 Agent 任务
- 攻击路径
- 关键命令线索
- 证据
- findings
- flag/loot
- Session writeup 草稿

Target 只存在于 Project Target Pool。Target Pool 负责承载：

- operator 初始添加的目标
- Agent 发现并提交准入的目标
- active / pending / rejected / archived 状态
- scope policy 派生出的允许边界

扫描任务必须显式引用 Target Pool 中 active 的 `target_id`。如果 Agent 从自然语言或工具结果中发现新目标，流程必须是 `propose_target(value)` -> 准入结果 -> 仅在 active 时调用扫描工具。

### 5.3 Task

Task 表示一次可执行动作。

Task 类型包括：

- `tool_invoke`，tool_invoke 包括 Agent 使用的各种工具，比如 `port_scan`、`dir_scan` 等，将来也会扩展工具
- `agent_analysis`
- `writeup_generate`

Task 必须记录：

- 所属 Project 和 Session
- 输入参数
- 执行器
- 状态
- 开始和结束时间
- 结构化结果
- 关联证据
- 错误信息

### 5.4 Evidence

Evidence 是可支撑判断的证据。

证据来源包括：

- 扫描结果
- HTTP 响应
- 用户手动笔记
- 文件、截图、payload、脚本
- POC 命中结果

Evidence 必须可以关联到：

- 攻击路径节点
- finding
- flag
- writeup 小节
- 原始 Task

### 5.5 Finding

Finding 是经过整理的发现或漏洞假设。

Finding 可以是：

- 开放服务
- Web 入口
- 可疑目录
- 技术栈识别
- 弱配置
- POC 命中
- exploit 候选
- 提权线索

Finding 不要求一定是正式漏洞，也可以是攻击路径中的关键线索。

### 5.6 Attack Path

Attack Path 是产品的核心视图。

攻击路径不是单纯时间线，而是将以下内容串联起来：

- 目标
- 资产
- 服务
- Web 入口
- 线索
- 假设
- 验证动作
- 证据
- 利用建议
- flag/loot
- 下一步行动

攻击路径节点必须能回答：

- 这个节点从哪里来
- 由哪个工具或命令发现
- 为什么重要
- 下一步建议是什么
- 是否已经验证

### 5.7 Flag and Loot

Flag 表示 CTF 关键成果。

Loot 表示有价值材料，例如：

- 凭据
- token
- 配置文件
- hash
- 私钥
- 数据库片段
- 可用于 pivot 的线索

系统必须允许用户手动标记 flag/loot，并关联来源证据。

## 6. 功能需求

### 6.1 Project 管理

系统必须支持：

- 创建 Project
- 打开最近 Project
- 列出 Project 内 Session
- 查看 Project 总览
- 归档 Project
- 生成 Project writeup 草稿

Project 总览必须展示：

- Session 数量
- 正在运行的 Task
- 已发现开放服务
- 已记录 finding
- 已记录 flag/loot
- 最近事件

### 6.2 Session 管理

系统必须支持：

- 创建目标 Session
- 绑定 IP、域名、URL 或备注
- 查看 Session dashboard
- 恢复历史事件
- 暂停或取消运行中的任务
- 重新运行历史任务
- 生成 Session writeup 草稿

Session dashboard 必须展示：

- 目标摘要
- 开放端口
- Web 入口
- 目录发现
- POC 命中
- 当前攻击路径
- 下一步建议
- 最近关键命令线索
- 证据和 flag

### 6.3 Agent 控制台

Agent 控制台必须包含：

- Chat 输入
- 流式输出
- 工具调用展示
- 扫描任务状态
- 下一步建议
- 解释信息

Agent 必须支持：

- 根据用户输入创建 Project 或 Session
- 根据当前目标自动选择枚举流程
- 根据扫描结果生成攻击路径节点
- 根据证据提出下一步建议
- 生成命令建议
- 生成 POC 验证建议
- 生成 writeup 草稿

Agent 输出必须避免黑盒化。用户必须能看到：

- Agent 准备执行什么
- 使用哪个工具
- 参数是什么
- 结果摘要是什么
- 为什么建议下一步

### 6.4 自动枚举

v1 自动枚举必须支持：

- 端口扫描
- 服务识别
- HTTP/HTTPS 探测
- 目录扫描
- nuclei POC 验证
- 结果归档
- 攻击路径更新

默认枚举策略：

1. 对目标执行端口扫描。
2. 对开放 HTTP/HTTPS 服务执行 HTTP 探测。
3. 对 Web 服务执行目录扫描。
4. 根据服务、标题、header、路径和指纹选择 POC 验证。
5. 生成 findings 和下一步建议。

### 6.5 扫描执行层

v1 扫描执行层采用混合模式：

- 默认集成本机工具 `nmap`
- 默认集成本机工具 `ffuf`
- 默认集成本机工具 `nuclei`
- 后端通过统一 Scanner Adapter 调用外部工具
- 保留后续 Go/Rust 自研执行器替换能力

执行器必须输出结构化结果，而不是只返回原始 stdout。

执行器必须保留原始输出作为 artifact，便于复盘和排错。

### 6.6 POC 与利用辅助

v1 支持 POC 验证和利用辅助，但不默认自动执行破坏性利用。

系统必须支持：

- nuclei 模板执行
- POC 命中结果展示
- 命中证据保存
- 根据 finding 生成利用建议
- 生成可复制命令
- 生成 exploit 脚本草稿
- 将用户执行结果关联回 finding

系统不应在用户未明确要求时自动执行：

- 写文件 webshell
- 删除或破坏数据
- 反连 shell
- 提权 exploit
- 持久化后门

### 6.7 外部命令执行

v1 不支持内置交互终端。

命令执行发生在系统外部，由用户在自有工具环境中完成。

系统在 v1 只负责：

- 生成命令建议
- 接收用户手动整理的命令结果、文件和笔记
- 将这些材料归档为 evidence、finding、attack path 和 writeup 的输入

### 6.8 攻击路径视图

攻击路径视图必须支持：

- 按目标展示节点
- 按阶段过滤
- 查看每个节点的来源证据
- 查看节点状态
- 查看下一步建议
- 手动添加节点
- 将外部命令结果关联到节点
- 将节点纳入 writeup

节点阶段建议：

- `recon`
- `service-enum`
- `web-enum`
- `vulnerability-hypothesis`
- `poc-verified`
- `exploit-assist`
- `privilege-escalation`
- `flag`
- `note`

### 6.9 结果可视化

结果可视化必须包含：

- 端口开放表
- 服务识别表
- Web 资产列表
- 目录发现列表
- POC 命中列表
- 攻击路径
- 事件时间线
- 证据列表
- flag/loot 列表

UI 应优先面向实战扫描和复盘，而不是营销型 dashboard。

### 6.10 Writeup 草稿

系统必须能生成 Markdown writeup 草稿。

草稿必须包含：

- Project 和 Session 基本信息
- 目标摘要
- 信息收集步骤
- 开放端口和服务
- Web 枚举结果
- 漏洞假设与验证过程
- 关键命令
- 证据引用
- flag/loot
- 未完成 TODO

Writeup 生成必须基于结构化数据和证据，不应只依赖聊天记录。

## 7. 数据与持久化需求

v1 使用：

- SQLite 保存结构化数据
- 文件系统保存 artifacts、原始输出、截图、脚本和 Markdown 报告

必须持久化：

- Project
- Session
- Task
- Event
- Evidence
- Finding
- AttackPathNode
- Flag
- Report

客户端关闭后重新打开，必须能恢复：

- Project 列表
- Session 状态
- 历史事件
- 扫描结果
- 攻击路径
- 已记录证据与报告
- writeup 草稿

## 8. 安全与边界

本产品面向用户自控授权的 CTF 靶场，不设计企业审批流。

v1 仍必须保留最小安全边界：

- Project 或 Session 必须声明目标范围
- 默认只对声明目标执行扫描
- 外部工具命令必须通过适配器参数化构造，避免字符串拼接注入
- 命令建议仅供用户在外部环境中自主执行
- 危险命令应有明显 UI 提示
- 所有网络任务必须记录目标、参数、开始时间和原始输出

安全边界目标是防止误扫、误执行和难以复盘，不是替代用户授权判断。

## 9. v1 验收标准

v1 完成时必须满足：

1. 用户能创建 Project 和目标 Session。
2. 用户能在桌面端通过 Chat 要求 Agent 枚举目标。
3. 后端能调用 `nmap` 生成端口和服务结果。
4. 对 HTTP 服务能调用 `ffuf` 生成目录发现。
5. 对候选目标能调用 `nuclei` 生成 POC 验证结果。
6. 所有扫描任务都有实时事件和最终状态。
7. 扫描结果能进入攻击路径视图。
8. 用户能把扫描结果、手动笔记或外部命令结果整理为证据。
9. 用户能记录 flag/loot。
10. 系统能生成 Markdown writeup 草稿。
11. 关闭并重启客户端后，数据可以恢复。
12. 外部工具缺失时，UI 和 API 返回可理解的诊断信息。

## 10. 后续演进

v1 之后可考虑：

- Go/Rust 自研高性能端口扫描器
- Go/Rust 自研目录扫描器
- 自定义 POC DSL
- 自动化 exploit playbook
- 多靶机攻击图谱
- AD/内网靶场 pivot 流程
- 截图采集和 Web 指纹增强
- 字典、payload、模板管理
- 浏览器自动化辅助
- 更完整的报告模板
