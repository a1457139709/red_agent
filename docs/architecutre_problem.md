1. Current Project Summary

这是一个本地单用户 CLI coding agent，已经具备“可用原型”级别的完整骨架，不再只是聊天壳子。核心结构已经分层清楚，主要在这些地方：

CLI 与命令路由：main.py
Agent loop / prompt / session state：agent
Task / Run / Checkpoint / Skill 服务层：app
Task runtime 编排：task_runner.py
技能系统：skills
SQLite 持久化：storage
工具与安全边界：tools
已实现的功能

本地交互式 CLI，带 Rich UI、分层 help、/clear、/reset
Base mode + explicit skill activation
SKILL.md 技能系统，支持 built-in 和 user-local skill
/skill use、/skill reload、/skill-name <prompt> 一次性调用
Task / Run / Checkpoint / TaskLog 持久化
public task ID / public run ID
/task create/list/find/recent/show/status/resume/detach/complete
/task runs/run/logs/checkpoints/checkpoint
blob-backed checkpoint：SQLite metadata + filesystem blob
capability-tier safety：read / write / execute / destructive
任务级 safety audit 和 tool event logging
基础 prompt + skill prompt + context summary 的 runtime 组合
17 个测试文件、约 70 个测试用例
已经做出来但还不够成熟的部分

安全模型有了，但还偏“本地守门员”，不是成熟产品级权限系统
技能系统有了，但还没有更强的插件生态、外部集成能力
任务系统可恢复，但还没有 autonomous/background runner
CLI 好很多了，但还没有 IDE / Web / mobile 多端协同
observability 已有，但导出、报告化、回放能力还比较弱
明显还未完善的问题

网络安全 skill 还只是起步，没有形成真正的安全工作流产品
没有项目级持久记忆机制，类似 CLAUDE.md 这种长期指令层还缺失
没有 MCP/外部工具协议层
没有 sub-agent / parallel delegation
没有 git-native 高阶工作流，比如 commit/PR/review automation
没有 non-interactive/script mode 的成熟接口
代码卫生还不够稳定：
仍有乱码注释/报错文本：registry.py, settings.py
仍有明显遗留文件：webSearch.py
文档/配置路径仍有命名不一致：README 有 .mini-claude-code，代码实际是 .red-code，见 README.md 与 settings.py
评分

架构设计：8/10
本地任务持久化与恢复：8/10
技能系统：7/10
安全边界：7/10
CLI 可用性：7.5/10
可观测性：7.5/10
技术选型：7.5/10
Python + SQLite + Rich 很合适
LangChain 能快速落地，但长期可控性和复杂度会拖分
代码质量：6.5/10
分层不错
但存在遗留代码、乱码、命名漂移、文档与实现不完全一致
整体成熟度：7/10（可用的本地 Agent 原型）
2. Compared With Mature Agents Like Claude Code

按 2026-04-01 我查的 Claude Code 官方文档，它已经覆盖：

多端：terminal / IDE / desktop / web
项目记忆：CLAUDE.md + auto memory
hooks
MCP 外部工具协议
subagents
permission modes / plan mode
scheduled tasks / remote workflows
更成熟的 git、CI、PR、automation 工作流
来源见：

Claude Code overview: https://code.claude.com/docs/en/overview
Memory: https://code.claude.com/docs/en/memory
Skills/slash commands: https://code.claude.com/docs/en/slash-commands
Hooks: https://code.claude.com/docs/en/hooks
Subagents: https://code.claude.com/docs/en/sub-agents
MCP: https://code.claude.com/docs/en/mcp
Permission modes: https://code.claude.com/docs/en/permission-modes
对比后的判断

你这个项目相对 Claude Code，已经完成了它最重要的一层地基：

本地 CLI
文件/命令工具
skill system
task/run/checkpoint persistence
基础 safety
基础 observability
也就是说，底座不差。
但如果按“成熟 Agent 产品”来比，目前大概只有 30% 到 40% 的成熟度。

不成熟但必要的缺失

这些是如果你想把它继续做成“真正强可用 Agent”，最好补的：

项目级长期记忆与规则系统
类似 CLAUDE.md
这是成熟 Agent 很关键的一层
更强的外部集成协议
类似 MCP / plugin API
sub-agent / parallel delegation
对大任务拆解非常关键
更成熟的 permission mode / plan mode
现在只有安全边界，还没有用户可切换的工作模式
git-native workflow
commit / diff / review / PR automation
更系统的 code hygiene 治理
清理乱码、遗留文件、命名不一致、文档漂移
不成熟但不一定必要的缺失

这些 Claude Code 有，但对你当前项目目标未必必须：

Web / desktop / mobile 多端
Remote control / cloud sessions
scheduled tasks
Slack / CI / browser extension 集成
组织级策略与多用户权限体系
企业级管理能力
一句话结论

这个项目现在已经不是 demo 了，属于**“本地单用户 Agent 的可用工程原型”**。
它最强的是：task-run-checkpoint-skill-safety 这条主干已经成型。
它最弱的是：memory / extensibility / multi-agent / workflow integration / code hygiene。

如果继续推进，我建议优先级是：

统一代码卫生与文档一致性
做项目级 memory / rules 系统
做 MCP-like integration layer
做 sub-agent / plan mode
再扩 security skills