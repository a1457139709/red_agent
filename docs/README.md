# mini-claude-code 文档导航

本目录记录的是当前 Python 版本 `mini-claude-code` 的实现说明。

## 当前优先阅读

1. [overview.md](./overview.md)
   项目定位、当前技术栈、目录入口
2. [architecture.md](./architecture.md)
   当前分层、运行链路、关键模块职责
3. [agent-loop.md](./agent-loop.md)
   Agent 主循环、`SessionState`、`ToolExecutor`、上下文压缩的协作方式
4. [architecture-improvement-report.md](./architecture-improvement-report.md)
   当前问题清单、P0/P1/P2 路线和改进建议
5. [engineering-development-plan.md](./engineering-development-plan.md)
   后续持续开发的内部工程蓝图、阶段路线与验收标准
6. [engineering-development-plan.en.md](./engineering-development-plan.en.md)
   English version of the internal engineering blueprint for future implementation work

## 专题文档

- [tools.md](./tools.md)
- [context.md](./context.md)
- [security.md](./security.md)
- [prompt-architecture.md](./prompt-architecture.md)

说明：

- 这些专题文档仍然保留了部分设计过程信息
- 其中个别示例代码不是最新实现
- 阅读时请优先以 `src/` 下真实代码和上面的当前文档为准

## 与代码对应的核心文件

```text
src/
├── main.py
├── agent/
│   ├── context.py
│   ├── loop.py
│   ├── provider.py
│   ├── settings.py
│   └── state.py
├── tools/
│   ├── __init__.py
│   ├── executor.py
│   ├── bash.py
│   ├── readFile.py
│   ├── writeFile.py
│   ├── editFile.py
│   ├── search.py
│   └── deleteFile.py
└── utils/
    ├── confirm.py
    ├── safety.py
    └── truncate.py
```
