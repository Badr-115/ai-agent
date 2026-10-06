import os
from typing import Any, Type

import google.generativeai as genai
from google.api_core.exceptions import NotFound
from pydantic import BaseModel

from .base import LLMProvider


class GeminiProvider(LLMProvider):

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set in the environment."
            )

        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        genai.configure(api_key=self.api_key)
        try:
            self.model = genai.GenerativeModel(model_name=self.model_name)
        except NotFound:
            self._report_model_not_found()
            raise

    def _report_model_not_found(self) -> None:
        supported_models = sorted(
            model.name
            for model in genai.list_models()
            if "generateContent" in model.supported_generation_methods
        )
        print(
            f"Gemini model '{self.model_name}' was not found. "
            "Models supporting generateContent: "
            f"{', '.join(supported_models) or '(none returned)'}"
        )

    @classmethod
    def _to_gemini_schema(
        cls,
        schema: dict[str, Any],
        definitions: dict[str, Any],
    ) -> dict[str, Any]:
        reference = schema.get("$ref")
        if reference:
            definition_name = reference.rsplit("/", 1)[-1]
            return cls._to_gemini_schema(
                definitions[definition_name],
                definitions,
            )

        alternatives = schema.get("anyOf")
        if alternatives:
            non_nullable = [
                option for option in alternatives
                if option.get("type") != "null"
            ]
            if len(non_nullable) == 1:
                converted = cls._to_gemini_schema(non_nullable[0], definitions)
                converted["nullable"] = True
                return converted

        schema_type = schema.get("type")
        gemini_schema: dict[str, Any] = {}
        if schema_type:
            gemini_schema["type"] = {
                "object": "OBJECT",
                "array": "ARRAY",
                "string": "STRING",
                "integer": "INTEGER",
                "number": "NUMBER",
                "boolean": "BOOLEAN",
            }[schema_type]

        if "description" in schema:
            gemini_schema["description"] = schema["description"]
        if "enum" in schema:
            gemini_schema["enum"] = schema["enum"]
        if "required" in schema:
            gemini_schema["required"] = schema["required"]
        if "properties" in schema:
            gemini_schema["properties"] = {
                name: cls._to_gemini_schema(property_schema, definitions)
                for name, property_schema in schema["properties"].items()
            }
        if "items" in schema:
            gemini_schema["items"] = cls._to_gemini_schema(
                schema["items"],
                definitions,
            )

        return gemini_schema

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
    ) -> BaseModel:
        json_schema = schema.model_json_schema()
        definitions = json_schema.get("$defs", {})
        response_schema = self._to_gemini_schema(
            json_schema,
            definitions,
        )
        model = self.model
        if system_prompt:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt,
            )

        try:
            response = await model.generate_content_async(
                contents=prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                },
            )
        except NotFound:
            self._report_model_not_found()
            raise

        result_text = response.text

        if not result_text:
            raise ValueError(
                "Gemini returned an empty response."
            )

        return schema.model_validate_json(result_text)