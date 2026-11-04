"""Gemini integration using the maintained google-genai Python SDK.

Network access, quota, and possible API charges occur ONLY when this provider
is explicitly selected. CI never instantiates it.
"""
import os
from typing import Type

from google import genai
from google.genai import types
from pydantic import BaseModel

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is missing; offline --demo requires no key.")
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(api_key=key)

    async def generate_structured(
        self, prompt: str, schema: Type[BaseModel],
        system_prompt: str | None = None,
    ) -> BaseModel:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system_prompt,
            temperature=0.2,
        )
        response = await self.client.aio.models.generate_content(
            model=self.model_name, contents=prompt, config=config,
        )
        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed
        if not response.text:
            raise ValueError("Model returned no structured JSON; no tool was executed.")
        return schema.model_validate_json(response.text)
