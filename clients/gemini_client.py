from __future__ import annotations

from google import genai
from google.genai import types

from clients.base_client import BaseClient


class GeminiClient(BaseClient):
    """Minimal Gemini API client used by Atlas Lite workers."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        timeout: int = 60,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key cannot be empty.")

        if not model_name.strip():
            raise ValueError("Gemini model name cannot be empty.")

        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self.model_name = model_name
        self.timeout = timeout
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=float(timeout)),
        )

    def generate(self, prompt: str) -> str:
        """Send one prompt to Gemini and return its text response."""
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ValueError("Prompt cannot be empty.")

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=cleaned_prompt,
        )

        response_text = getattr(response, "text", None)
        if not response_text:
            raise RuntimeError("Gemini returned an empty response.")

        return response_text
