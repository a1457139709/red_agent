from __future__ import annotations

from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import socket
import ssl

import pytest

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import AdmissionRequest, ScopeValidator, TargetDescriptor
from tools import build_security_tool_registry, build_tool_registry, get_security_tools, get_tools
from tools.security.banner_grab import BannerGrabSecurityTool
from tools.security.dns_lookup import DnsLookupSecurityTool, _build_query
from tools.security.http_probe import HttpProbeSecurityTool
from tools.security.port_scan import PortScanSecurityTool
from tools.security.tls_inspect import TlsInspectSecurityTool


def make_policy(**kwargs) -> ScopePolicy:
    return ScopePolicy.create(operation_id="op-1", **kwargs)


def make_target_descriptor(
    *,
    raw_target: str,
    host: str,
    port: int | None = None,
    protocol: str | None = None,
    normalized_target: str | None = None,
) -> TargetDescriptor:
    return TargetDescriptor(
        raw_target=raw_target,
        kind="host",
        host=host,
        ip=host if host.replace(".", "").isdigit() else None,
        port=port,
        protocol=protocol,
        normalized_target=normalized_target or raw_target,
    )


class _TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.end_headers()
            return
        if self.path == "/final":
            payload = b"redirect target"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = b"hello from security tool"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


def run_http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def run_banner_server(banner: bytes):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve_once():
        conn, _addr = listener.accept()
        with conn:
            try:
                _data = conn.recv(1024)
            except Exception:
                pass
            conn.sendall(banner)
        listener.close()

    thread = Thread(target=serve_once, daemon=True)
    thread.start()
    return port, thread


def build_dns_response() -> bytes:
    question = _build_query(query_id=0x1337, record_type="A", name="example.com")[12:]
    answer = b"\xc0\x0c" + b"\x00\x01\x00\x01" + b"\x00\x00\x01," + b"\x00\x04" + bytes(
        [93, 184, 216, 34]
    )
    header = b"\x13\x37\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
    return header + question + answer


def test_security_tool_registry_keeps_legacy_and_v2_families_separate():
    legacy_names = {tool.name for tool in get_tools()}
    security_names = {tool.name for tool in get_security_tools()}

    assert set(build_tool_registry()) == legacy_names
    assert set(build_security_tool_registry()) == security_names
    assert security_names == {
        "dns_lookup",
        "http_probe",
        "tls_inspect",
        "banner_grab",
        "port_scan",
    }
    assert legacy_names.isdisjoint(security_names)


def test_http_probe_returns_structured_result():
    server, thread = run_http_server()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/demo"
        tool = HttpProbeSecurityTool()
        invocation = tool.validate_invocation(target=url, arguments={}, policy=make_policy())
        target = make_target_descriptor(
            raw_target=url,
            host="127.0.0.1",
            port=port,
            protocol="http",
            normalized_target=url,
        )

        result = tool.execute(invocation, target)

        assert result.payload["status_code"] == 200
        assert result.payload["body_snippet"] == "hello from security tool"
        assert result.evidence_candidates[0].evidence_type == "http_response"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_probe_returns_first_redirect_response_without_following():
    server, thread = run_http_server()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/redirect"
        tool = HttpProbeSecurityTool()
        invocation = tool.validate_invocation(target=url, arguments={}, policy=make_policy())
        target = make_target_descriptor(
            raw_target=url,
            host="127.0.0.1",
            port=port,
            protocol="http",
            normalized_target=url,
        )

        result = tool.execute(invocation, target)

        assert result.payload["status_code"] == 302
        assert result.payload["final_url"] == url
        assert result.payload["location"] == "/final"
        assert result.payload["body_snippet"] == ""
        assert result.target == url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dns_lookup_parses_structured_answers(monkeypatch):
    response = build_dns_response()

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            self.sent = None

        def settimeout(self, value):
            self.timeout = value

        def sendto(self, payload, destination):
            self.sent = (payload, destination)

        def recvfrom(self, size):
            return response, ("8.8.8.8", 53)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("tools.security.dns_lookup.socket.socket", FakeSocket)

    tool = DnsLookupSecurityTool()
    invocation = tool.validate_invocation(target="example.com", arguments={"record_type": "A"}, policy=make_policy())
    admission_request = invocation.to_admission_request(
        operation_id="op-1",
        job_id="job-1",
        tool_name=tool.name,
        tool_category=tool.category,
    )
    target = make_target_descriptor(
        raw_target="8.8.8.8",
        host="8.8.8.8",
        port=53,
        protocol="dns",
        normalized_target="8.8.8.8:53",
    )

    result = tool.execute(invocation, target)

    assert admission_request.raw_target == "8.8.8.8"
    assert admission_request.additional_targets[0].raw_target == "example.com"
    assert admission_request.additional_targets[0].label == "query_name"
    assert result.payload["answers"][0]["value"] == "93.184.216.34"
    assert result.payload["execution_target"] == "8.8.8.8:53"
    assert result.evidence_candidates[0].title.startswith("DNS A results")
    assert result.target == "example.com"


def test_tls_inspect_emits_conservative_findings(monkeypatch):
    calls = []
    cert = {
        "subject": ((("commonName", "example.com"),),),
        "issuer": ((("commonName", "example.com"),),),
        "subjectAltName": (("DNS", "example.com"),),
        "notBefore": "Jan 01 00:00:00 2030 GMT",
        "notAfter": "Jan 01 00:00:00 2021 GMT",
        "serialNumber": "01",
    }

    def fake_handshake(*, host, port, timeout_seconds, verified):
        calls.append((host, port, timeout_seconds, verified))
        if verified:
            raise ssl.SSLCertVerificationError(1, "hostname mismatch")
        return cert, "TLSv1.3", ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256), None

    monkeypatch.setattr("tools.security.tls_inspect._handshake", fake_handshake)

    tool = TlsInspectSecurityTool()
    invocation = tool.validate_invocation(target="example.com:443", arguments={}, policy=make_policy())
    target = make_target_descriptor(
        raw_target="example.com:443",
        host="example.com",
        port=443,
        protocol="tls",
        normalized_target="example.com:443",
    )

    result = tool.execute(invocation, target)
    finding_types = {finding.finding_type for finding in result.finding_candidates}

    assert calls[0][3] is True
    assert calls[1][3] is False
    assert "tls_hostname_mismatch" in finding_types
    assert "tls_self_signed_certificate" in finding_types
    assert "tls_expired_certificate" in finding_types
    assert "tls_not_yet_valid_certificate" in finding_types


def test_banner_grab_reads_banner_and_emits_findings():
    port, thread = run_banner_server(b"+PONG redis ready\r\n")
    tool = BannerGrabSecurityTool()
    target_ref = f"127.0.0.1:{port}"
    invocation = tool.validate_invocation(
        target=target_ref,
        arguments={"probe": "redis"},
        policy=make_policy(),
    )
    target = make_target_descriptor(
        raw_target=target_ref,
        host="127.0.0.1",
        port=port,
        protocol="tcp",
        normalized_target=target_ref,
    )

    result = tool.execute(invocation, target)
    thread.join(timeout=2)

    assert "redis ready" in result.payload["banner"]
    assert any(finding.finding_type == "redis_banner" for finding in result.finding_candidates)


def test_port_scan_scans_requested_ports_and_returns_open_ports():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        open_port = listener.getsockname()[1]

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as closed_socket:
            closed_socket.bind(("127.0.0.1", 0))
            closed_port = closed_socket.getsockname()[1]
        tool = PortScanSecurityTool()
        policy = make_policy(allowed_ports=[open_port, closed_port])
        invocation = tool.validate_invocation(
            target="127.0.0.1",
            arguments={"ports": [open_port, closed_port], "timeout_seconds": 1},
            policy=policy,
        )
        target = make_target_descriptor(
            raw_target="127.0.0.1",
            host="127.0.0.1",
            protocol="tcp",
            normalized_target="127.0.0.1",
        )

        result = tool.execute(invocation, target)

    assert open_port in result.payload["open_ports"]
    statuses = {entry["port"]: entry["status"] for entry in result.payload["ports"]}
    assert statuses[open_port] == "open"
    assert statuses[closed_port] in {"closed", "error"}


def test_port_scan_refuses_ports_outside_policy_before_execution():
    tool = PortScanSecurityTool()
    policy = make_policy(allowed_ports=[80])

    with pytest.raises(ValueError, match="outside the scope policy"):
        tool.validate_invocation(
            target="127.0.0.1",
            arguments={"ports": [81]},
            policy=policy,
        )


def test_scope_validator_checks_metadata_port_lists():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_domains=["example.com"],
        allowed_protocols=["tcp"],
        allowed_ports=[80, 443],
    )
    request = AdmissionRequest(
        operation_id="op-1",
        job_id="job-1",
        tool_name="port_scan",
        tool_category="recon",
        raw_target="example.com",
        protocol="tcp",
        metadata={"ports": [80, 443]},
    )

    decision = validator.evaluate(policy, request)

    assert decision.outcome == "allowed"
