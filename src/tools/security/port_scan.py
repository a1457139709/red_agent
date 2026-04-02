from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from time import perf_counter
import re
import subprocess

from domain.operations import ScopePolicy
from domain.scope import ScopePolicyService, validate_hostname, validate_ip, validate_port
from tools.contracts import EvidenceItem, PortScanBackendResult, PortScanRequest, SecurityToolResult


_PORT_STATE_RE = re.compile(r"^(?P<port>\d+)/tcp\s+(?P<state>\S+)\s*(?P<service>\S+)?", re.MULTILINE)
_RANGE_RE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")


@dataclass(frozen=True, slots=True)
class _TargetDescriptor:
    kind: str
    value: str


class PortScanTool:
    name = "port_scan"

    def __init__(self, scope_policy_service: ScopePolicyService) -> None:
        self.scope_policy_service = scope_policy_service

    def execute(self, request: PortScanRequest) -> SecurityToolResult:
        validation = self._validate_request(request)
        if validation is not None:
            return validation

        target = self._classify_target(request.target, request.validated_scope)
        if isinstance(target, SecurityToolResult):
            return target

        requested_ports = self._collect_ports(request)
        blocked = self._check_scope(request.validated_scope, target, requested_ports)
        if blocked is not None:
            return blocked

        try:
            backend_result = self._run_nmap(target.value, request, requested_ports)
        except FileNotFoundError:
            return self._failed_result(
                summary="nmap is not installed or not available on PATH",
                structured_result={
                    "scanner": "nmap",
                    "target": target.value,
                    "target_kind": target.kind,
                    "requested_ports": requested_ports,
                },
                stderr="nmap executable not found",
            )
        except subprocess.TimeoutExpired:
            return self._failed_result(
                summary=f"port_scan timed out after {request.timeout_seconds} seconds",
                structured_result={
                    "scanner": "nmap",
                    "target": request.target,
                    "requested_ports": requested_ports,
                },
                stderr="scan timed out",
            )

        return self._build_result(target, requested_ports, backend_result)

    def _validate_request(self, request: PortScanRequest) -> SecurityToolResult | None:
        if request.validated_scope is None:
            return self._failed_result(
                summary="port_scan requires a validated scope policy",
                structured_result={},
            )
        if request.timeout_seconds < 1:
            return self._failed_result(
                summary="port_scan timeout_seconds must be at least 1",
                structured_result={"target": request.target},
            )
        if not request.ports and not request.port_ranges:
            return self._failed_result(
                summary="port_scan requires at least one explicit port or port range",
                structured_result={"target": request.target},
            )
        try:
            self._collect_ports(request)
        except ValueError as exc:
            return self._failed_result(
                summary=str(exc),
                structured_result={"target": request.target},
            )
        return None

    def _classify_target(self, target: str, scope: ScopePolicy) -> _TargetDescriptor | SecurityToolResult:
        try:
            return _TargetDescriptor(kind="ip", value=validate_ip(target))
        except ValueError:
            pass

        target_candidate = target.strip().lower()
        if "/" in target_candidate:
            return self._failed_result(
                summary=f"Unsupported target kind for port_scan: {target}",
                structured_result={"target": target, "target_kind": "cidr"},
            )
        if target_candidate in scope.allowed_domains:
            return self._failed_result(
                summary=f"Unsupported target kind for port_scan: {target}",
                structured_result={"target": target, "target_kind": "domain"},
            )
        try:
            return _TargetDescriptor(kind="hostname", value=validate_hostname(target))
        except ValueError:
            return self._failed_result(
                summary=f"Invalid port_scan target: {target}",
                structured_result={"target": target},
            )

    def _collect_ports(self, request: PortScanRequest) -> list[int]:
        collected: set[int] = set()
        for port in request.ports or []:
            collected.add(validate_port(port))
        for port_range in request.port_ranges or []:
            collected.update(self._expand_range(port_range))
        return sorted(collected)

    def _expand_range(self, value: str) -> list[int]:
        match = _RANGE_RE.fullmatch(value.strip())
        if not match:
            raise ValueError(f"Invalid port range: {value}")
        start = validate_port(int(match.group("start")))
        end = validate_port(int(match.group("end")))
        if end < start:
            raise ValueError(f"Invalid port range: {value}")
        return list(range(start, end + 1))

    def _check_scope(
        self,
        scope: ScopePolicy,
        target: _TargetDescriptor,
        requested_ports: list[int],
    ) -> SecurityToolResult | None:
        for port in requested_ports:
            kwargs = {"port": port, "protocol": "tcp"}
            kwargs[target.kind] = target.value
            decision = self.scope_policy_service.check_target(scope, **kwargs)
            if not decision.allowed:
                return SecurityToolResult(
                    status="blocked",
                    summary=decision.message,
                    structured_result={
                        "scanner": "nmap",
                        "target": target.value,
                        "target_kind": target.kind,
                        "requested_ports": requested_ports,
                        "blocked_reason": decision.reason_code,
                    },
                    evidence_items=[],
                    finding_candidates=[],
                    metrics={"requested_port_count": len(requested_ports)},
                )
        return None

    def _run_nmap(
        self,
        target: str,
        request: PortScanRequest,
        requested_ports: list[int],
    ) -> PortScanBackendResult:
        argv = ["nmap", "-Pn", "-p", self._to_portspec(requested_ports), target]
        started = perf_counter()
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds,
            check=False,
        )
        duration_ms = int((perf_counter() - started) * 1000)
        return PortScanBackendResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
        )

    def _to_portspec(self, ports: list[int]) -> str:
        return ",".join(str(port) for port in ports)

    def _build_result(
        self,
        target: _TargetDescriptor,
        requested_ports: list[int],
        backend_result: PortScanBackendResult,
    ) -> SecurityToolResult:
        port_states = self._parse_port_states(backend_result.stdout)
        state_counts = Counter(entry["state"] for entry in port_states)
        open_ports = [entry["port"] for entry in port_states if entry["state"] == "open"]
        structured = {
            "scanner": "nmap",
            "target": target.value,
            "target_kind": target.kind,
            "requested_ports": requested_ports,
            "open_ports": open_ports,
            "port_states": port_states,
            "state_counts": dict(state_counts),
            "argv": backend_result.argv,
            "returncode": backend_result.returncode,
        }
        evidence_items = [
            EvidenceItem(
                evidence_type="port_scan_raw_stdout",
                title="nmap stdout",
                summary="Raw stdout from nmap port scan",
                content_type="text/plain",
                content=backend_result.stdout or "",
                filename_hint="nmap-stdout",
            ),
            EvidenceItem(
                evidence_type="port_scan_result",
                title="normalized port scan result",
                summary="Normalized structured result for port scan",
                content_type="application/json",
                content=self._to_json(structured),
                filename_hint="port-scan-result",
            ),
        ]
        if backend_result.stderr:
            evidence_items.append(
                EvidenceItem(
                    evidence_type="port_scan_stderr",
                    title="nmap stderr",
                    summary="stderr from nmap port scan",
                    content_type="text/plain",
                    content=backend_result.stderr,
                    filename_hint="nmap-stderr",
                )
            )

        summary = (
            f"Scanned {len(requested_ports)} requested TCP ports on {target.value}: "
            f"{len(open_ports)} open"
        )

        if backend_result.returncode != 0:
            return self._failed_result(
                summary=f"nmap exited with code {backend_result.returncode}",
                structured_result=structured,
                stdout=backend_result.stdout,
                stderr=backend_result.stderr,
                metrics={
                    "requested_port_count": len(requested_ports),
                    "open_port_count": len(open_ports),
                    "duration_ms": backend_result.duration_ms,
                },
                evidence_items=evidence_items,
            )

        return SecurityToolResult(
            status="succeeded",
            summary=summary,
            structured_result=structured,
            evidence_items=evidence_items,
            finding_candidates=[],
            metrics={
                "requested_port_count": len(requested_ports),
                "open_port_count": len(open_ports),
                "closed_port_count": state_counts.get("closed", 0),
                "filtered_port_count": state_counts.get("filtered", 0),
                "duration_ms": backend_result.duration_ms,
            },
        )

    def _parse_port_states(self, stdout: str) -> list[dict[str, str | int | None]]:
        parsed: list[dict[str, str | int | None]] = []
        for match in _PORT_STATE_RE.finditer(stdout):
            parsed.append(
                {
                    "port": int(match.group("port")),
                    "state": match.group("state"),
                    "service": match.group("service"),
                }
            )
        return parsed

    def _failed_result(
        self,
        *,
        summary: str,
        structured_result: dict,
        stdout: str | None = None,
        stderr: str | None = None,
        metrics: dict | None = None,
        evidence_items: list[EvidenceItem] | None = None,
    ) -> SecurityToolResult:
        local_evidence = list(evidence_items or [])
        if stdout:
            local_evidence.append(
                EvidenceItem(
                    evidence_type="port_scan_raw_stdout",
                    title="nmap stdout",
                    summary="Raw stdout from failed nmap port scan",
                    content_type="text/plain",
                    content=stdout,
                    filename_hint="nmap-stdout",
                )
            )
        if stderr:
            local_evidence.append(
                EvidenceItem(
                    evidence_type="port_scan_stderr",
                    title="nmap stderr",
                    summary="stderr from failed nmap port scan",
                    content_type="text/plain",
                    content=stderr,
                    filename_hint="nmap-stderr",
                )
            )
        return SecurityToolResult(
            status="failed",
            summary=summary,
            structured_result=structured_result,
            evidence_items=local_evidence,
            finding_candidates=[],
            metrics=metrics or {},
        )

    def _to_json(self, payload: dict) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
