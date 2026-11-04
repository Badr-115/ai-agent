"""Host tool outcomes are distinct from untrusted model assertions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolOutcome:
    tool: str
    ok: bool
    summary: str
    feedback: str
    verification: bool = False
