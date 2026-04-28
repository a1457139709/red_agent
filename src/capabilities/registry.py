from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from models.capability import CapabilityKind, LoadedCapability
from models.session import SessionMode

from .loader import CapabilityLoadError, load_capability_from_file


class CapabilityRegistry:
    def __init__(
        self,
        roots: list[tuple[str, Path]] | Path,
        *,
        known_tool_names: set[str] | None = None,
    ) -> None:
        if isinstance(roots, Path):
            self.roots = [("custom", roots)]
        else:
            self.roots = list(roots)
        self.known_tool_names = None if known_tool_names is None else set(known_tool_names)
        self._cache: dict[str, LoadedCapability] | None = None

    @classmethod
    def built_in(cls, *, known_tool_names: set[str] | None = None) -> "CapabilityRegistry":
        return cls(
            [("built-in", Path(__file__).resolve().parent)],
            known_tool_names=known_tool_names,
        )

    @classmethod
    def built_in_and_local(
        cls,
        *,
        local_root: Path,
        known_tool_names: set[str] | None = None,
    ) -> "CapabilityRegistry":
        return cls(
            [
                ("built-in", Path(__file__).resolve().parent),
                ("local", local_root),
            ],
            known_tool_names=known_tool_names,
        )

    def reload(self) -> None:
        self._cache = None

    def list_capabilities(
        self,
        *,
        kind: CapabilityKind | str | None = None,
        mode: SessionMode | str | None = None,
    ) -> list[LoadedCapability]:
        capabilities = list(self._load_all().values())
        if kind is not None:
            normalized_kind = CapabilityKind(kind)
            capabilities = [
                capability for capability in capabilities if capability.manifest.kind == normalized_kind
            ]
        if mode is not None:
            normalized_mode = SessionMode(mode)
            capabilities = [
                capability for capability in capabilities if normalized_mode in capability.manifest.modes
            ]
        return sorted(capabilities, key=lambda capability: capability.manifest.name)

    def get_capability(self, name: str) -> LoadedCapability | None:
        return self._load_all().get(name)

    def require_capability(self, name: str) -> LoadedCapability:
        capability = self.get_capability(name)
        if capability is None:
            raise CapabilityLoadError(f"Capability not found: {name}")
        return capability

    def _load_all(self) -> dict[str, LoadedCapability]:
        if self._cache is not None:
            return self._cache

        capabilities: dict[str, LoadedCapability] = {}
        for source, root_dir in self.roots:
            if not root_dir.exists():
                continue
            for entry in sorted(root_dir.iterdir()):
                if not entry.is_dir():
                    continue
                manifest_file = entry / "capability.json"
                if not manifest_file.exists():
                    continue
                loaded = self._load_capability(entry, manifest_file, source=source)
                capabilities[loaded.manifest.name] = loaded

        self._cache = capabilities
        return self._cache

    def _load_capability(
        self,
        entry: Path,
        manifest_file: Path,
        *,
        source: str,
    ) -> LoadedCapability:
        loaded = load_capability_from_file(manifest_file)
        if loaded.manifest.name != entry.name:
            raise CapabilityLoadError(
                f"Capability name '{loaded.manifest.name}' does not match directory '{entry.name}'"
            )
        if self.known_tool_names is not None:
            unknown_tools = sorted(
                tool_name
                for tool_name in loaded.manifest.tools.allowed
                if tool_name not in self.known_tool_names
            )
            if unknown_tools:
                raise CapabilityLoadError(
                    f"Capability '{loaded.manifest.name}' declares unknown tools: {', '.join(unknown_tools)}"
                )
        return replace(loaded, source=source)
