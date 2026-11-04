"""Strict, auditable model-to-tool protocol.

The model only chooses an action. The host owns validation and permissions.
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Action = Literal["list_files", "read_file", "search_text", "preview_file", "write_file", "run_check", "finish"]


class AgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    reason: str = Field(min_length=1, max_length=350)
    path: str | None = Field(default=None, max_length=240)
    query: str | None = Field(default=None, max_length=150)
    content: str | None = Field(default=None, max_length=120_000)
    command: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=800)


class RunStatus(str, Enum):
    INSPECTED = "inspected"
    VERIFIED_LOCAL = "verified_local"
    UNVERIFIED_CHANGES = "unverified_changes"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class AuditEvent(BaseModel):
    step: int
    tool: str
    ok: bool
    summary: str = Field(max_length=1000)


class AgentReport(BaseModel):
    goal: str
    status: RunStatus
    steps: int
    files_changed: list[str] = Field(default_factory=list)
    events: list[AuditEvent] = Field(default_factory=list)
    summary: str = ""
    warning: str = "Local checks are not a security certification or production deployment."
    model_calls: int = 0
