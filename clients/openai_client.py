from __future__ import annotations

from openai import OpenAI

from clients.base_client import BaseClient


class OpenAIClient(BaseClient):
    """
    OpenAI provider implementation used by the Atlas Lite Manager.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
    ) -> None:

        if not api_key.strip():
            raise ValueError("OpenAI API key cannot be empty.")

        if not model_name.strip():
            raise ValueError("OpenAI model name cannot be empty.")

        self.model_name = model_name
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str) -> str:

        cleaned_prompt = prompt.strip()

        if not cleaned_prompt:
            raise ValueError("Prompt cannot be empty.")

        response = self.client.responses.create(
            model=self.model_name,
            input=cleaned_prompt,
        )

        return response.output_text.strip()
