from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
import uuid

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AgentMode(str, Enum):
    GENERAL = "GENERAL"

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    max_retries: int = Field(default=3)
    result: Optional[str] = None
    error: Optional[str] = None

class Plan(BaseModel):
    goal: str
    tasks: List[Task]
    mode: AgentMode
