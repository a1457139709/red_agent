from __future__ import annotations

from dataclasses import dataclass

from .contracts import ScannerAdapter
from .ffuf_adapter import FfufAdapter
from .nmap_adapter import NmapAdapter
from .nuclei_adapter import NucleiAdapter


@dataclass(frozen=True, slots=True)
class ScannerRegistry:
    adapters: dict[str, ScannerAdapter]
    task_types: dict[str, str]

    def require_by_tool(self, tool_name: str) -> ScannerAdapter:
        adapter = self.adapters.get(tool_name)
        if adapter is None:
            raise ValueError(f"Unknown scanner tool: {tool_name}")
        return adapter

    def require_by_task_type(self, task_type: str) -> ScannerAdapter:
        tool_name = self.task_types.get(task_type)
        if tool_name is None:
            raise ValueError(f"Unsupported scan task type: {task_type}")
        return self.require_by_tool(tool_name)


def build_scanner_registry() -> ScannerRegistry:
    adapters = {
        "nmap": NmapAdapter(),
        "ffuf": FfufAdapter(),
        "nuclei": NucleiAdapter(),
    }
    return ScannerRegistry(
        adapters=adapters,
        task_types={adapter.task_type: name for name, adapter in adapters.items()},
    )
