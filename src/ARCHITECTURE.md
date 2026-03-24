# mini-claude-code 架构文档

## 1. 系统概览

mini-claude-code 是一个运行在用户本地终端的 Code Agent，专为编程和开发任务设计。它基于 LangChain 框架构建，具有文件操作、Shell 命令执行、网络访问等能力。

### 当前运行环境
- **操作系统**: Microsoft Windows 10 专业版 (64-bit)
- **Python 版本**: Python 3.12.0
- **工作目录**: `D:\Project\Python\Agent\src`

## 2. 核心架构

```
src/
├── main.py                # 主程序入口，处理用户交互和会话管理
├── SYSTEM_PROMPT.md       # 系统提示词，定义 agent 角色和行为准则
├── agent/
│   ├── loop.py            # Agent 执行循环核心逻辑
│   ├── provider.py        # 模型提供者配置
│   └── prompt.py          # 系统提示词组装
├── tools/
│   ├── __init__.py        # 工具自动导入
│   ├── registry.py        # 工具注册中心
│   ├── readFile.py        # 文件读取工具
│   ├── writeFile.py       # 文件写入工具
│   ├── editFile.py        # 文件编辑工具
│   ├── bash.py            # Shell 命令执行工具
│   ├── deleteFile.py      # 文件删除工具
│   ├── listDir.py         # 目录列表工具
│   └── webSearch.py       # 网络搜索工具
├── utils/
│   ├── safety.py          # 路径安全检查
│   └── truncate.py        # 工具输出截断
└── README.md              # 项目说明
```

## 3. 核心组件说明

### 3.1 主程序 (main.py)
- 处理用户输入和命令解析（`/help`, `/reset`, `/exit`）
- 管理会话历史（history）
- 实现上下文压缩机制
- 调用 agent_loop 执行核心逻辑

### 3.2 Agent 循环 (agent/loop.py)
- 构建系统提示词（包含上下文摘要）
- 创建 LangChain Agent 实例
- 注册所有可用工具
- 执行 Agent 并返回结果

### 3.3 工具系统 (tools/)
- **read_file**: 读取文件内容，支持分段读取
- **write_file**: 写入文件内容（全量覆盖）
- **edit_file**: 替换文件中的特定字符串（局部修改）
- **bash**: 执行 Shell 命令
- **delete_file**: 删除指定文件
- **list_dir**: 列出目录内容
- **web_search**: 网络搜索（当前未启用）

## 4. 功能评估与增强建议

### 4.1 当前功能完整性
✅ **基础功能完备**: 文件操作、Shell 执行、目录浏览等核心功能已实现
✅ **安全机制完善**: 路径安全检查、敏感文件提示、危险命令确认
✅ **用户体验良好**: 命令行交互、帮助系统、会话管理

### 4.2 建议增强功能

#### 🔧 实用性增强
- **代码分析工具**: 添加静态代码分析、语法检查、代码质量评估
- **Git 集成**: `git_status`, `git_commit`, `git_push` 等 Git 操作工具
- **调试工具**: `debug_python` - 运行 Python 代码并捕获错误
- **API 测试工具**: `http_request` - 发送 HTTP 请求并分析响应

#### 🛡️ 安全性增强
- **沙箱执行**: 对 bash 命令添加更严格的白名单限制
- **文件权限检查**: 在文件操作前检查读写权限
- **资源限制**: 限制 bash 命令执行时间和内存使用

#### 📊 智能性增强
- **自动上下文压缩**: 根据 token 使用量自动触发上下文压缩
- **多步任务规划**: 支持复杂任务的分步执行和状态跟踪
- **代码生成优化**: 添加代码风格检查和最佳实践建议

#### 🌐 扩展性增强
- **插件系统**: 支持动态加载外部工具插件
- **配置管理**: YAML 配置文件管理工具启用状态和参数
- **日志系统**: 完整的操作日志记录和审计功能

## 5. 使用示例

```bash
# 查看帮助
> /help

# 读取文件
> read_file file_path="main.py" limit=10

# 编辑文件
> edit_file file_path="main.py" old_string="print(\"mini-claude-code\")" new_string="print(\"mini-claude-code v1.0\")"

# 执行命令
> bash command="dir"
```

## 6. 开发指南

- **新增工具**: 在 `tools/` 目录下创建新文件，使用 `@register_tool` 装饰器
- **修改提示词**: 编辑 `SYSTEM_PROMPT.md` 和 `agent/prompt.py`
- **调试 Agent**: 修改 `main.py` 中的调试代码段
- **测试工具**: 运行 `test.py` 进行单元测试

---
*文档生成时间: $(date)*