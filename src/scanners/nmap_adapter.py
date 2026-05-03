from __future__ import annotations

from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .contracts import AttackPathCandidate, ScannerEvidenceCandidate


class NmapAdapter:
    name = "nmap"
    task_type = "port_scan"
    output_filename = "nmap.xml"
    output_content_type = "application/xml"

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        target_host = _required_text(input_data.get("target_host") or input_data.get("target"), "target_host")
        ports = _normalize_ports(input_data.get("ports"))
        normalized: dict[str, Any] = {"target_host": target_host}
        if ports:
            normalized["ports"] = ports
        return normalized

    def build_argv(self, *, binary_path: str, input_data: dict[str, Any], output_path: Path) -> list[str]:
        argv = [binary_path, "-oX", str(output_path), "-sV"]
        ports = input_data.get("ports") or []
        if ports:
            argv.extend(["-p", ",".join(str(port) for port in ports)])
        argv.append(str(input_data["target_host"]))
        return argv

    def parse_output(self, output_text: str) -> dict[str, Any]:
        if not output_text.strip():
            return {"open_ports": [], "hosts": []}
        root = ET.fromstring(output_text)
        hosts: list[dict[str, Any]] = []
        open_ports: list[dict[str, Any]] = []
        for host_node in root.findall("host"):
            addresses = [
                {"addr": node.attrib.get("addr"), "addrtype": node.attrib.get("addrtype")}
                for node in host_node.findall("address")
            ]
            host_ports: list[dict[str, Any]] = []
            for port_node in host_node.findall("./ports/port"):
                state = port_node.find("state")
                if state is None or state.attrib.get("state") != "open":
                    continue
                service = port_node.find("service")
                entry = {
                    "port": int(port_node.attrib["portid"]),
                    "protocol": port_node.attrib.get("protocol", "tcp"),
                    "service": service.attrib.get("name") if service is not None else None,
                    "product": service.attrib.get("product") if service is not None else None,
                    "version": service.attrib.get("version") if service is not None else None,
                }
                host_ports.append(entry)
                open_ports.append(entry)
            hosts.append({"addresses": addresses, "open_ports": host_ports})
        return {"open_ports": open_ports, "hosts": hosts}

    def build_evidence(
        self,
        *,
        input_data: dict[str, Any],
        structured: dict[str, Any],
        output_path: Path,
    ) -> tuple[list[ScannerEvidenceCandidate], list[AttackPathCandidate]]:
        evidence: list[ScannerEvidenceCandidate] = []
        attack_path: list[AttackPathCandidate] = []
        for port in structured.get("open_ports", []):
            service = port.get("service") or "unknown"
            title = f"Open {port.get('protocol', 'tcp')} port {port['port']} ({service})"
            evidence.append(
                ScannerEvidenceCandidate(
                    evidence_type="service",
                    title=title,
                    summary=f"nmap found {title} on {input_data['target_host']}.",
                    payload=port,
                    content_ref=str(output_path),
                )
            )
            attack_path.append(
                AttackPathCandidate(
                    stage="enumeration",
                    title=title,
                    source_ref=str(output_path),
                    next_action=f"Probe {service} on port {port['port']}.",
                )
            )
        return evidence, attack_path


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty.")
    return value.strip()


def _normalize_ports(value: object) -> list[int]:
    if value in (None, ""):
        return []
    raw_items = value
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    if not isinstance(raw_items, list):
        raise ValueError("ports must be a list or comma-separated string.")
    ports: list[int] = []
    for item in raw_items:
        if item in (None, ""):
            continue
        port = int(item)
        if port < 1 or port > 65535:
            raise ValueError("ports must be between 1 and 65535.")
        ports.append(port)
    return ports
