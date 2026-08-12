from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

CompileBackendName = Literal[
    "auto",
    "local-metaeditor",
    "wine-metaeditor",
    "remote-worker",
    "github-actions",
]


@dataclass(frozen=True)
class CompileRequest:
    target: Path
    project_root: Path
    evidence_dir: Path
    timeout_sec: int = 180
    policy: dict[str, int | bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BackendCapability:
    name: str
    available: bool
    native_windows: bool
    release_authority: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompileBackend(Protocol):
    name: str

    def capability(self) -> BackendCapability: ...

    def execute(self, request: CompileRequest) -> dict[str, Any]: ...


AUTO_BACKEND_ORDER: tuple[str, ...] = (
    "local-metaeditor",
    "github-actions",
    "remote-worker",
    "wine-metaeditor",
)


def choose_auto_backend(capabilities: dict[str, BackendCapability]) -> str | None:
    """Choose the strongest configured backend without upgrading trust implicitly."""
    for name in AUTO_BACKEND_ORDER:
        capability = capabilities.get(name)
        if capability and capability.available:
            return name
    return None
