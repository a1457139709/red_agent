from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .contracts import AttackPathCandidate, ScannerEvidenceCandidate


class NucleiAdapter:
    name = "nuclei"
    task_type = "poc_scan"
    output_filename = "nuclei.jsonl"
    output_content_type = "application/jsonl"

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        target = _required_text(input_data.get("target_url") or input_data.get("target"), "target_url")
        normalized: dict[str, Any] = {"target_url": target}
        templates = input_data.get("templates")
        if templates not in (None, ""):
            if isinstance(templates, str):
                templates = [templates]
            if not isinstance(templates, list):
                raise ValueError("templates must be a string or list.")
            template_paths = []
            for template in templates:
                template_path = Path(str(template)).expanduser()
                if not template_path.exists():
                    raise ValueError(f"nuclei template path does not exist: {template}")
                template_paths.append(str(template_path))
            normalized["templates"] = template_paths
        return normalized

    def build_argv(self, *, binary_path: str, input_data: dict[str, Any], output_path: Path) -> list[str]:
        argv = [binary_path, "-target", str(input_data["target_url"]), "-jsonl", "-o", str(output_path)]
        for template in input_data.get("templates", []):
            argv.extend(["-t", str(template)])
        return argv

    def parse_output(self, output_text: str) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        for line in output_text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            info = item.get("info") if isinstance(item.get("info"), dict) else {}
            matches.append(
                {
                    "template_id": item.get("template-id") or item.get("template_id"),
                    "name": info.get("name"),
                    "severity": info.get("severity"),
                    "matched_url": item.get("matched-at") or item.get("matched_at"),
                    "extracted_results": item.get("extracted-results") or item.get("extracted_results") or [],
                    "metadata": info.get("metadata") or {},
                }
            )
        return {"matches": matches}

    def build_evidence(
        self,
        *,
        input_data: dict[str, Any],
        structured: dict[str, Any],
        output_path: Path,
    ) -> tuple[list[ScannerEvidenceCandidate], list[AttackPathCandidate]]:
        evidence = [
            ScannerEvidenceCandidate(
                evidence_type="poc_hit",
                title=f"{item.get('severity') or 'unknown'} nuclei match {item.get('template_id')}",
                summary=item.get("name"),
                payload=item,
                content_ref=str(output_path),
            )
            for item in structured.get("matches", [])
        ]
        attack_path = [
            AttackPathCandidate(
                stage="poc-verified",
                title=f"Validate nuclei match {item.get('template_id')}",
                status="verified",
                source_ref=str(output_path),
                next_action="Manually verify impact and exploitability.",
            )
            for item in structured.get("matches", [])
        ]
        return evidence, attack_path


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty.")
    return value.strip()
