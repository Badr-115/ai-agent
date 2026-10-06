import os
from typing import Type

from groq import AsyncGroq
from pydantic import BaseModel

from .base import LLMProvider


class GroqProvider(LLMProvider):

    def __init__(
        self,
        model_name: str = "openai/gpt-oss-20b",
    ):
        self.api_key = os.getenv("GROQ_API_KEY")

        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is not set in the environment."
            )

        self.client = AsyncGroq(
            api_key=self.api_key
        )

        self.model_name = model_name

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
    ) -> BaseModel:

        messages = []

        # إضافة System Prompt إذا كان موجودًا
        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        # إضافة طلب المستخدم
        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        # إنشاء JSON Schema من Pydantic
        json_schema = schema.model_json_schema()

        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": json_schema,
                },
            },
        )

        result_text = response.choices[0].message.content

        if not result_text:
            raise ValueError(
                "Groq returned an empty response."
            )

        return schema.model_validate_json(result_text)