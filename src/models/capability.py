from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from models.risk_policy import RiskLevel
from models.session import SessionMode


class CapabilityKind(StrEnum):
    SKILL = "skill"
    MODULE = "module"


class CapabilityExecutionStyle(StrEnum):
    PROMPT_ASSIST = "prompt_assist"
    TYPED_TOOL = "typed_tool"
    WORKFLOW = "workflow"


class CapabilityParameterType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass(frozen=True, slots=True)
class CapabilityParameter:
    name: str
    type: CapabilityParameterType
    required: bool
    description: str
    default: Any | None = None
    choices: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityToolPolicy:
    allowed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityRiskMetadata:
    default: RiskLevel
    actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityExecutionMetadata:
    style: CapabilityExecutionStyle
    profile: str


@dataclass(frozen=True, slots=True)
class CapabilitySessionSupport:
    supports_one_shot: bool
    supports_persistent: bool
    result_layers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    version: int
    name: str
    kind: CapabilityKind
    display_name: str
    description: str
    modes: tuple[SessionMode, ...]
    parameters: tuple[CapabilityParameter, ...]
    tools: CapabilityToolPolicy
    risk: CapabilityRiskMetadata
    execution: CapabilityExecutionMetadata
    session: CapabilitySessionSupport
    metadata: dict[str, Any] = field(default_factory=dict)
    argument_hint: str | None = None
    user_invocable: bool | None = None
    disable_model_invocation: bool | None = None
    model: str | None = None
    effort: str | None = None
    shell: str | None = None

    def parameter_map(self) -> dict[str, CapabilityParameter]:
        return {parameter.name: parameter for parameter in self.parameters}

    @property
    def is_user_invocable(self) -> bool:
        return self.user_invocable is not False

    @property
    def allows_model_invocation(self) -> bool:
        return not bool(self.disable_model_invocation)


@dataclass(frozen=True, slots=True)
class LoadedCapability:
    manifest: CapabilityManifest
    root_dir: Path
    manifest_file: Path
    source: str = "unknown"
    references: tuple[Path, ...] = field(default_factory=tuple)
    scripts: tuple[Path, ...] = field(default_factory=tuple)
    prompt_file: Path | None = None
    prompt_body: str = ""


@dataclass(frozen=True, slots=True)
class ModuleInvocationRequest:
    module: LoadedCapability
    parameters: dict[str, Any]
    mode: SessionMode
    one_shot: bool
    session_id: str | None
    execution_profile: str
    execution_style: CapabilityExecutionStyle
    allowed_tools: tuple[str, ...]
    risk_default: RiskLevel
    risk_actions: tuple[str, ...]
    result_layers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModuleExecutionStep:
    tool_name: str
    target: str
    arguments: dict[str, Any]
    summary: str = ""

    def tool_arguments(self) -> dict[str, Any]:
        return {"target": self.target, **dict(self.arguments)}


@dataclass(frozen=True, slots=True)
class ModuleExecutionPlan:
    invocation: ModuleInvocationRequest
    steps: tuple[ModuleExecutionStep, ...]
