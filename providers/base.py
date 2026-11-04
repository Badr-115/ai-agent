"""Typed interface for providers returning validated Pydantic objects."""
from abc import ABC, abstractmethod
from typing import Type

from pydantic import BaseModel


class LLMProvider(ABC):
    @abstractmethod
    async def generate_structured(
        self, prompt: str, schema: Type[BaseModel],
        system_prompt: str | None = None,
    ) -> BaseModel:
        """Return a validated model, or raise; never execute tools here."""
