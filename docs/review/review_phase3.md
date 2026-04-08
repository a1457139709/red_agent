[P1] admission.py:67
确认后执行的请求仍会绕过并发和速率限制，这是当前最重要的问题，直接削弱了 Phase 2/3 的执行边界。

[P1] dns_lookup.py:193
dns_lookup 的真实网络目标是 nameserver，不是 admission 校验过的查询名，因此当前实现允许越界 DNS 出站流量。

[P1] http_probe.py:105
http_probe 自动跟随重定向，可能在首跳合法的情况下继续访问未授权主机，属于明确的 scope bypass。

[P2] security_tool_execution_service.py:47
未知 job_type 会直接抛错，但不会把 job 标记为失败，也不会留下日志，排障体验和可审计性都不够。