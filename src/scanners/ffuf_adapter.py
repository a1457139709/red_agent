from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .contracts import AttackPathCandidate, ScannerEvidenceCandidate


class FfufAdapter:
    name = "ffuf"
    task_type = "dir_scan"
    output_filename = "ffuf.json"
    output_content_type = "application/json"

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        base_url = _required_text(input_data.get("base_url") or input_data.get("target"), "base_url")
        wordlist = _required_text(input_data.get("wordlist"), "wordlist")
        wordlist_path = Path(wordlist).expanduser()
        if not wordlist_path.is_file():
            raise ValueError(f"wordlist does not exist: {wordlist}")
        url = base_url if "FUZZ" in base_url else f"{base_url.rstrip('/')}/FUZZ"
        normalized: dict[str, Any] = {"base_url": base_url, "url": url, "wordlist": str(wordlist_path)}
        filters = input_data.get("filters")
        if filters is not None:
            if not isinstance(filters, dict):
                raise ValueError("filters must be an object.")
            normalized["filters"] = dict(filters)
        return normalized

    def build_argv(self, *, binary_path: str, input_data: dict[str, Any], output_path: Path) -> list[str]:
        argv = [
            binary_path,
            "-u",
            str(input_data["url"]),
            "-w",
            str(input_data["wordlist"]),
            "-of",
            "json",
            "-o",
            str(output_path),
        ]
        filters = input_data.get("filters") or {}
        for option, flag in (("status_codes", "-fc"), ("size", "-fs"), ("words", "-fw"), ("lines", "-fl")):
            value = filters.get(option)
            if value not in (None, ""):
                argv.extend([flag, str(value)])
        return argv

    def parse_output(self, output_text: str) -> dict[str, Any]:
        if not output_text.strip():
            return {"results": []}
        payload = json.loads(output_text)
        results = payload.get("results", [])
        if not isinstance(results, list):
            results = []
        parsed_results = []
        for item in results:
            if not isinstance(item, dict):
                continue
            parsed_results.append(
                {
                    "url": item.get("url"),
                    "input": item.get("input"),
                    "status": item.get("status"),
                    "length": item.get("length"),
                    "words": item.get("words"),
                    "lines": item.get("lines"),
                    "redirectlocation": item.get("redirectlocation"),
                }
            )
        return {"results": parsed_results}

    def build_evidence(
        self,
        *,
        input_data: dict[str, Any],
        structured: dict[str, Any],
        output_path: Path,
    ) -> tuple[list[ScannerEvidenceCandidate], list[AttackPathCandidate]]:
        evidence = [
            ScannerEvidenceCandidate(
                evidence_type="web_path",
                title=f"Discovered path {item.get('url')}",
                summary=f"ffuf found HTTP {item.get('status')} for {item.get('url')}.",
                payload=item,
                content_ref=str(output_path),
            )
            for item in structured.get("results", [])
        ]
        attack_path = [
            AttackPathCandidate(
                stage="web-enumeration",
                title=f"Review discovered path {item.get('url')}",
                source_ref=str(output_path),
                next_action="Check page content and authentication behavior.",
            )
            for item in structured.get("results", [])
        ]
        return evidence, attack_path


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty.")
    return value.strip()
