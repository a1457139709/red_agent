# 项目概览

## 定位

`mini-claude-code` 是一个运行在本地终端里的 Python Code Agent。

它当前更偏“教学型工程原型”：

- 有真实的多轮对话入口
- 有真实的文件和命令工具
- 有基础的上下文压缩和安全约束
- 代码结构足够小，适合继续扩展和重构

## 当前技术栈

| 模块 | 当前实现 | 说明 |
|------|----------|------|
| Runtime | Python 3.12 | 当前项目主语言 |
| LLM 接入 | `langchain-openai` | 对接 OpenAI 兼容接口 |
| Agent 循环 | 手写 LangChain tool-calling loop | 便于教学和控制边界 |
| 配置 | `.env` + `Settings` | 统一收口运行参数 |
| 状态管理 | `SessionState` | 管理历史、压缩摘要、usage |
| 工具执行 | `ToolExecutor` | 统一确认、敏感提示和执行 |
| 测试 | `pytest` | 基础回归用例 |

## 当前目录入口

```text
.
├── README.md
├── pyproject.toml
├── requirements.txt
├── docs/
├── src/
│   ├── main.py
│   ├── agent/
│   ├── tools/
│   └── utils/
├── tests/
└── test/              # 旧的实验脚本
```

## 运行方式

```bash
pip install -r requirements.txt
python src/main.py
pytest
```

## 当前实现目标

通过这个项目，你可以快速看清一个本地 Code Agent 的最小骨架：

1. CLI 如何驱动多轮会话
2. LLM 如何与工具回环
3. 工具安全边界应该放在哪一层
4. 上下文压缩如何和会话状态协作
5. 工程化补齐之后，项目如何开始可维护

## 关键模块

- `src/main.py`
  CLI 入口，负责用户交互、会话推进、压缩触发
- `src/agent/loop.py`
  Agent 主循环，驱动模型与工具往返
- `src/agent/settings.py`
  统一读取和校验运行配置
- `src/agent/state.py`
  统一管理运行态会话状态
- `src/tools/executor.py`
  统一处理命令确认、敏感路径提示和工具调用
- `src/agent/context.py`
  负责上下文压缩和结构化摘要
