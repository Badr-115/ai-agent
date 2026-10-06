from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

class LLMProvider(ABC):
    @abstractmethod
    async def generate_structured(self, prompt: str, schema: BaseModel, system_prompt: Optional[str] = None) -> BaseModel:
        pass
