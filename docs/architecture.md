# 当前架构

## 分层结构

```text
CLI Layer
  └── src/main.py

Application State Layer
  ├── src/agent/settings.py
  └── src/agent/state.py

Agent Runtime Layer
  ├── src/agent/loop.py
  ├── src/agent/context.py
  ├── src/agent/prompt.py
  └── src/agent/provider.py

Tool Execution Layer
  └── src/tools/executor.py

Tool Layer
  ├── src/tools/bash.py
  ├── src/tools/readFile.py
  ├── src/tools/writeFile.py
  ├── src/tools/editFile.py
  ├── src/tools/search.py
  ├── src/tools/deleteFile.py
  └── src/tools/listDir.py

Infrastructure / Utility Layer
  ├── src/utils/safety.py
  ├── src/utils/confirm.py
  └── src/utils/truncate.py
```

## 运行链路

```text
用户输入
  ↓
main.py
  ↓
SessionState / Settings
  ↓
agent.loop.agent_loop()
  ↓
ChatOpenAI.bind_tools(tools)
  ↓
模型输出 tool_calls
  ↓
ToolExecutor.execute()
  ↓
工具结果回填为 ToolMessage
  ↓
模型继续推理或返回最终答案
  ↓
必要时触发 context.compress_context()
```

## 各层职责

### 1. CLI Layer

`src/main.py` 负责：

- 接收终端输入
- 处理 `/help`、`/reset`、`/exit`
- 初始化 `Settings`、`SessionState`、`ToolExecutor`
- 在一轮对话结束后决定是否触发压缩

### 2. Application State Layer

`Settings` 负责统一承载：

- 模型配置
- 最大步数
- 上下文阈值
- 工作目录

`SessionState` 负责统一承载：

- 历史消息
- 压缩摘要
- 最近一次 usage

这层的目标是避免运行态状态散落在多个局部变量里。

### 3. Agent Runtime Layer

`agent/loop.py` 是主控逻辑：

- 组装系统提示词
- 创建模型
- 绑定工具
- 驱动 tool-calling 循环
- 控制最大步数

`agent/context.py` 负责：

- 判断是否需要压缩
- 调用模型压缩历史消息
- 产出结构化 `CompressionSummary`

### 4. Tool Execution Layer

`tools/executor.py` 统一处理工具调用前后的控制逻辑：

- 命令风险检测
- 用户确认
- 敏感路径提示
- 工具名到工具对象的分发

这样工具本身只做执行，不再直接承担 CLI 交互职责。

### 5. Tool Layer

当前显式装配的工具有：

- `bash`
- `read_file`
- `write_file`
- `edit_file`
- `search`
- `delete_file`
- `list_dir`

工具注册由 `src/tools/__init__.py` 显式定义，不再依赖自动扫描导入副作用。

## 当前架构的改进点

相比早期实现，当前架构已经完成了几项关键治理：

- 用 `Settings` 替代散落的环境变量读取
- 用 `SessionState` 替代松散的历史和摘要变量
- 用 `ToolExecutor` 把确认和展示从工具函数中抽离
- 用显式工具装配替代 import 副作用注册
- 为上下文压缩补了结构化 `CompressionSummary`
