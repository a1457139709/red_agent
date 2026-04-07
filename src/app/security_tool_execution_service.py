from __future__ import annotations

from agent.settings import Settings, get_settings
from models.job import JobLogLevel
from runtime.timeouts import run_with_timeout
from tools import build_security_tool_registry
from tools.executor import SecurityToolExecutionError, SecurityToolExecutor

from .job_service import JobService
from .operation_service import OperationService
from .scoped_execution_service import ConfirmCallback, ScopedExecutionResult, ScopedExecutionService


class SecurityToolExecutionService:
    def __init__(
        self,
        *,
        job_service: JobService,
        operation_service: OperationService,
        scoped_execution_service: ScopedExecutionService,
        security_tool_executor: SecurityToolExecutor,
        settings: Settings,
    ) -> None:
        self.job_service = job_service
        self.operation_service = operation_service
        self.scoped_execution_service = scoped_execution_service
        self.security_tool_executor = security_tool_executor
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SecurityToolExecutionService":
        settings = settings or get_settings()
        return cls(
            job_service=JobService.from_settings(settings),
            operation_service=OperationService.from_settings(settings),
            scoped_execution_service=ScopedExecutionService.from_settings(settings),
            security_tool_executor=SecurityToolExecutor(build_security_tool_registry()),
            settings=settings,
        )

    def execute_job(
        self,
        *,
        job_identifier: str,
        confirm: ConfirmCallback = None,
    ) -> ScopedExecutionResult:
        job = self.job_service.require_job(job_identifier)
        operation = self.operation_service.require_operation(job.operation_id)
        policy = self.operation_service.require_scope_policy(operation.id)
        try:
            tool = self.security_tool_executor.get_tool(job.job_type)
            self.job_service.write_log(
                job_identifier=job.id,
                level=JobLogLevel.INFO,
                message="security_tool_validation_started",
                payload={"tool_name": job.job_type, "target_ref": job.target_ref},
            )
            invocation = self.security_tool_executor.validate(
                job.job_type,
                target=job.target_ref,
                arguments=self._effective_arguments(job.arguments, timeout_seconds=job.timeout_seconds),
                policy=policy,
            )
        except SecurityToolExecutionError as exc:
            return self._validation_failed(job_identifier=job.id, tool_name=job.job_type, error=exc.error)

        request = invocation.to_admission_request(
            operation_id=operation.id,
            job_id=job.id,
            tool_name=tool.name,
            tool_category=tool.category,
        )

        result = self.scoped_execution_service.execute(
            request=request,
            executor=lambda _request, target: run_with_timeout(
                lambda: self.security_tool_executor.execute(
                    tool.name,
                    invocation=invocation,
                    target=target,
                ),
                timeout_seconds=invocation.timeout_seconds,
            ),
            confirm=confirm,
        )
        self.job_service.write_log(
            job_identifier=job.id,
            level=JobLogLevel.INFO if result.status == "succeeded" else JobLogLevel.ERROR,
            message=f"security_tool_execution_{result.status}",
            payload={
                "tool_name": tool.name,
                "message": result.message,
            },
        )
        return result

    def _effective_arguments(self, arguments: dict, *, timeout_seconds: int | None) -> dict:
        effective_arguments = dict(arguments)
        if timeout_seconds is not None:
            effective_arguments["timeout_seconds"] = timeout_seconds
        return effective_arguments

    def _validation_failed(
        self,
        *,
        job_identifier: str,
        tool_name: str,
        error: str,
    ) -> ScopedExecutionResult:
        self.job_service.write_log(
            job_identifier=job_identifier,
            level=JobLogLevel.ERROR,
            message="security_tool_validation_failed",
            payload={"error": error, "tool_name": tool_name},
        )
        return ScopedExecutionResult(
            status="failed",
            message=error,
            decision=None,
            result=None,
        )
