[P1] worker.py:90
长任务执行期间不会续租，lease 会在正常执行中到期，scheduler 可能提前回收并重试同一个 job，造成重复执行和状态冲突。

[P1] security_tool_execution_service.py:97
job.timeout_seconds 不是硬约束，arguments.timeout_seconds 可以覆盖它，实际会绕过 Phase 4 的 per-job timeout。

[P2] scheduler.py:47
带 operation_identifier 的 scheduler pass 仍会全局恢复 stale lease，作用域不一致，容易误改其他 operation 的 job。