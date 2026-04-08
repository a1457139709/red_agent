# Commit 规范

本项目中的 Agent 在编写提交信息时，必须遵循 Conventional Commits 规范，保证历史可读、可检索、可自动生成变更日志。

## 基本格式

推荐格式：

```text
<type>(<scope>)!?: <description>
```

说明：

- `type` 必填，使用小写英文
- `scope` 可选，表示影响范围，推荐使用模块、目录或功能名
- `!` 可选，表示存在破坏性变更
- `description` 必填，简洁描述本次提交做了什么

## 编写要求

- 首行使用单行摘要，不写句号
- 摘要应聚焦单一变更，避免把无关修改混在同一个提交中
- `description` 使用清晰、具体的动作描述，避免使用 `update`、`misc`、`fix bug` 这类模糊表述
- 行为变化、接口变化或文档示例变化时，提交中应包含相应文档更新
- 如果存在破坏性变更，使用 `!` 或在 footer 中补充 `BREAKING CHANGE:`

## 常用类型

- `feat`: 新功能
- `fix`: 缺陷修复
- `refactor`: 重构，但不新增功能也不修复用户可见缺陷
- `docs`: 文档更新
- `test`: 测试新增或调整
- `chore`: 杂项维护，不影响产品功能
- `build`: 构建系统或依赖管理变更
- `ci`: CI/CD 配置变更
- `perf`: 性能优化
- `style`: 不影响语义的样式调整
- `revert`: 回滚已有提交

## Scope 建议

`scope` 建议尽量稳定且可读，例如：

- `cli`
- `app`
- `storage`
- `models`
- `tools`
- `docs`
- `tests`
- `agents`

如果一次修改明确只影响某个子模块，优先填写 `scope`；如果影响面较广，也可以省略。

## 推荐示例

```text
feat(cli): add explicit skill activation flag
fix(storage): handle missing checkpoint blob metadata
refactor(app): split operation service into focused modules
docs(agents): add commit convention guide
test(cli): cover topic drill-down help output
chore(deps): bump langchain-core to latest pinned version
```

## 破坏性变更示例

```text
feat(api)!: remove legacy task resume endpoint
```

或：

```text
refactor(storage): replace legacy checkpoint layout

BREAKING CHANGE: checkpoint files created before v2 must be migrated
```

## Agent 执行规则

- 每次提交只表达一个明确意图
- 先完成代码、测试和文档，再生成提交信息
- 不为旧实现保留低质量兼容层；如果必须移除旧行为，明确标记破坏性变更
- 提交信息应准确反映最终落盘内容，不得先写结论再让代码凑内容

## 不推荐示例

以下写法应避免：

```text
update code
fix bug
misc
chore: change stuff
```

这些摘要信息过于模糊，无法帮助后续维护者快速理解提交目的。
