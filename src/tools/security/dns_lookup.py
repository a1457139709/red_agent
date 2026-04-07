from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any
import socket
import struct

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import TargetDescriptor
from tools.contracts import (
    EvidenceCandidate,
    ScopeTarget,
    SecurityToolInvocation,
    SecurityToolResult,
    normalize_timeout,
    require_non_empty_target,
)

DNS_PORT = 53
DEFAULT_NAMESERVER = "8.8.8.8"
DNS_QUERY_FLAGS = 0x0100
DNS_CLASS_IN = 1
RECORD_TYPE_TO_CODE = {
    "A": 1,
    "NS": 2,
    "CNAME": 5,
    "PTR": 12,
    "MX": 15,
    "TXT": 16,
    "AAAA": 28,
}
CODE_TO_RECORD_TYPE = {value: key for key, value in RECORD_TYPE_TO_CODE.items()}


def _encode_name(name: str) -> bytes:
    parts = name.strip(".").split(".")
    encoded = bytearray()
    for part in parts:
        label = part.encode("idna")
        if not label or len(label) > 63:
            raise ValueError("DNS labels must be between 1 and 63 bytes.")
        encoded.append(len(label))
        encoded.extend(label)
    encoded.append(0)
    return bytes(encoded)


def _read_name(message: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    current_offset = offset
    jumped = False
    next_offset = offset

    while True:
        if current_offset >= len(message):
            raise ValueError("Malformed DNS response: name exceeds packet bounds.")
        length = message[current_offset]
        if length == 0:
            current_offset += 1
            if not jumped:
                next_offset = current_offset
            break
        if length & 0xC0 == 0xC0:
            if current_offset + 1 >= len(message):
                raise ValueError("Malformed DNS response: pointer exceeds packet bounds.")
            pointer = ((length & 0x3F) << 8) | message[current_offset + 1]
            if not jumped:
                next_offset = current_offset + 2
            current_offset = pointer
            jumped = True
            continue
        current_offset += 1
        label_bytes = message[current_offset : current_offset + length]
        if len(label_bytes) != length:
            raise ValueError("Malformed DNS response: label exceeds packet bounds.")
        labels.append(label_bytes.decode("idna"))
        current_offset += length
        if not jumped:
            next_offset = current_offset
    return ".".join(labels), next_offset


def _build_query(*, query_id: int, record_type: str, name: str) -> bytes:
    question = _encode_name(name) + struct.pack("!HH", RECORD_TYPE_TO_CODE[record_type], DNS_CLASS_IN)
    header = struct.pack("!HHHHHH", query_id, DNS_QUERY_FLAGS, 1, 0, 0, 0)
    return header + question


def _parse_rdata(message: bytes, *, record_type_code: int, rdata_offset: int, rdlength: int) -> object:
    rdata = message[rdata_offset : rdata_offset + rdlength]
    if record_type_code == RECORD_TYPE_TO_CODE["A"] and rdlength == 4:
        return socket.inet_ntop(socket.AF_INET, rdata)
    if record_type_code == RECORD_TYPE_TO_CODE["AAAA"] and rdlength == 16:
        return socket.inet_ntop(socket.AF_INET6, rdata)
    if record_type_code in {
        RECORD_TYPE_TO_CODE["CNAME"],
        RECORD_TYPE_TO_CODE["NS"],
        RECORD_TYPE_TO_CODE["PTR"],
    }:
        value, _ = _read_name(message, rdata_offset)
        return value
    if record_type_code == RECORD_TYPE_TO_CODE["MX"]:
        if rdlength < 3:
            raise ValueError("Malformed DNS response: MX answer too short.")
        preference = struct.unpack_from("!H", message, rdata_offset)[0]
        exchange, _ = _read_name(message, rdata_offset + 2)
        return {"preference": preference, "exchange": exchange}
    if record_type_code == RECORD_TYPE_TO_CODE["TXT"]:
        values: list[str] = []
        cursor = 0
        while cursor < len(rdata):
            chunk_length = rdata[cursor]
            cursor += 1
            chunk = rdata[cursor : cursor + chunk_length]
            values.append(chunk.decode("utf-8", errors="replace"))
            cursor += chunk_length
        return values
    return rdata.hex()


def _parse_response(message: bytes, *, query_id: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if len(message) < 12:
        raise ValueError("Malformed DNS response: packet too short.")
    (
        response_id,
        flags,
        question_count,
        answer_count,
        authority_count,
        additional_count,
    ) = struct.unpack_from("!HHHHHH", message, 0)
    if response_id != query_id:
        raise ValueError("DNS response ID does not match the request.")
    rcode = flags & 0x000F
    if rcode != 0:
        raise ValueError(f"DNS server returned error code {rcode}.")

    offset = 12
    for _ in range(question_count):
        _name, offset = _read_name(message, offset)
        offset += 4

    answers: list[dict[str, Any]] = []
    for _ in range(answer_count):
        name, offset = _read_name(message, offset)
        record_type_code, record_class, ttl, rdlength = struct.unpack_from("!HHIH", message, offset)
        offset += 10
        rdata_offset = offset
        offset += rdlength
        if record_class != DNS_CLASS_IN:
            continue
        answers.append(
            {
                "name": name,
                "record_type": CODE_TO_RECORD_TYPE.get(record_type_code, str(record_type_code)),
                "ttl": ttl,
                "value": _parse_rdata(
                    message,
                    record_type_code=record_type_code,
                    rdata_offset=rdata_offset,
                    rdlength=rdlength,
                ),
            }
        )

    metadata = {
        "flags": flags,
        "question_count": question_count,
        "answer_count": answer_count,
        "authority_count": authority_count,
        "additional_count": additional_count,
    }
    return answers, metadata


class DnsLookupSecurityTool:
    name = "dns_lookup"
    category = "recon"

    def validate_invocation(
        self,
        *,
        target: str,
        arguments: Mapping[str, Any],
        policy: ScopePolicy,
    ) -> SecurityToolInvocation:
        del policy
        query_name = require_non_empty_target(target).strip(".")
        record_type = str(arguments.get("record_type", "A")).strip().upper()
        if record_type not in RECORD_TYPE_TO_CODE:
            supported = ", ".join(sorted(RECORD_TYPE_TO_CODE))
            raise ValueError(f"record_type must be one of: {supported}.")
        timeout_seconds = normalize_timeout(arguments.get("timeout_seconds"))
        nameserver = str(arguments.get("nameserver", DEFAULT_NAMESERVER)).strip()
        if not nameserver:
            raise ValueError("nameserver is required.")
        return SecurityToolInvocation(
            target=query_name,
            timeout_seconds=timeout_seconds,
            protocol="dns",
            port=DNS_PORT,
            admission_target=nameserver,
            admission_protocol="dns",
            admission_port=DNS_PORT,
            additional_scope_targets=(
                ScopeTarget(
                    target=query_name,
                    protocol="dns",
                    port=DNS_PORT,
                    label="query_name",
                ),
            ),
            metadata={"record_type": record_type},
            execution_args={
                "query_name": query_name,
                "record_type": record_type,
                "nameserver": nameserver,
            },
        )

    def execute(
        self,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult:
        query_name = str(invocation.execution_args["query_name"])
        record_type = str(invocation.execution_args["record_type"])
        nameserver = str(invocation.execution_args["nameserver"])
        query_id = 0x1337
        query = _build_query(query_id=query_id, record_type=record_type, name=query_name)

        started = perf_counter()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(invocation.timeout_seconds)
                client.sendto(query, (nameserver, DNS_PORT))
                response, _remote = client.recvfrom(4096)
        except Exception as exc:
            raise ValueError(f"dns_lookup failed: {exc}.") from exc
        duration_ms = round((perf_counter() - started) * 1000, 2)

        answers, response_metadata = _parse_response(response, query_id=query_id)
        summary = (
            f"DNS {record_type} lookup for {query_name} returned {len(answers)} answer(s) "
            f"via {nameserver}."
        )
        payload = {
            "query_name": query_name,
            "record_type": record_type,
            "nameserver": nameserver,
            "execution_target": target.normalized_target,
            "answers": answers,
            "response": response_metadata,
            "query_time_ms": duration_ms,
        }
        evidence = EvidenceCandidate(
            evidence_type="dns_response",
            target_ref=query_name,
            title=f"DNS {record_type} results for {query_name}",
            summary=summary,
            content_type="application/json",
            payload=payload,
        )
        return SecurityToolResult(
            tool_name=self.name,
            target=query_name,
            summary=summary,
            payload=payload,
            evidence_candidates=[evidence],
        )
