# Agent Loop 设计

## 核心目标

Agent Loop 的职责很单纯：

1. 把当前会话状态转换成模型输入
2. 调用模型
3. 如果模型发起工具调用，就执行工具并回填结果
4. 如果模型停止调用工具，就返回最终答案
5. 如果达到最大步数仍未完成，就返回明确失败态

## 当前实现位置

- 主循环：`src/agent/loop.py`
- 会话状态：`src/agent/state.py`
- 配置：`src/agent/settings.py`
- 工具执行：`src/tools/executor.py`
- 上下文压缩：`src/agent/context.py`

## 当前循环结构

```python
async def agent_loop(question, session_state, tool_executor, settings):
    system_prompt = await assemble_system_prompt(session_state.context_summary)
    model = create_model(settings).bind_tools(tool_executor.get_tools())

    messages = [
        SystemMessage(content=system_prompt),
        *session_state.history,
        HumanMessage(content=question),
    ]

    for _ in range(settings.max_agent_steps):
        ai_message = await model.ainvoke(messages)

        if not ai_message.tool_calls:
            return final_result

        messages.append(ai_message)

        for tool_call in ai_message.tool_calls:
            tool_result = tool_executor.execute(tool_call["name"], tool_call["args"])
            tool_message = ToolMessage(content=tool_result, tool_call_id=tool_call["id"])
            messages.append(tool_message)
```

## 关键设计点

### 1. `SessionState` 负责会话输入边界

主循环不再直接接收松散的 `history` 和 `context_summary`，而是统一接收 `SessionState`。

这样可以明确：

- 哪些消息属于历史
- 当前压缩摘要是什么
- 最近一次 usage 是什么

### 2. `ToolExecutor` 负责工具执行边界

主循环不再直接调用 `tool.invoke(...)`，而是交给 `ToolExecutor`。

这样可以把：

- 危险命令阻断
- 用户确认
- 敏感路径提示

统一放在工具执行层，而不是散落在每个工具函数内部。

### 3. 多工具调用的消息结构保持正确

一条 `AIMessage` 只会追加一次，随后再按顺序追加多条 `ToolMessage`。

这避免了早期实现里“同一条 assistant 消息被重复插入历史”的问题。

### 4. 最大步数有显式失败态

当循环跑满仍未完成时，主循环会返回：

- `status = "max_steps_exceeded"`
- 一个明确的用户可读提示
- 当前累计步骤消息

这样 CLI 层就能稳定处理，而不是落成通用异常。

## 与上下文压缩的协作

主循环本身不直接做压缩，只负责返回本轮消息和 usage。

CLI 层在一轮完成后：

1. 把用户消息和本轮消息写回 `SessionState`
2. 根据 usage 判断是否触发压缩
3. 若需要，则调用 `compress_context(...)`
4. 将 `CompressionSummary` 重新转成提示词片段，写回 `SessionState.compressed_summary`

这样主循环只关心“执行当前轮次”，压缩逻辑留给更外层控制。

## 当前测试覆盖

`tests/test_agent_loop.py` 当前覆盖了两个基础场景：

- 多工具调用时不会重复追加 `AIMessage`
- 达到最大步数时会返回 `max_steps_exceeded`

这让后续继续改 Agent Loop 时，有了最基本的回归保护。
