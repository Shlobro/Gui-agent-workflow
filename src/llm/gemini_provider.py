"""Gemini CLI provider."""

from typing import List, Optional, Tuple
from .base_provider import BaseLLMProvider, LLMProviderRegistry


class GeminiProvider(BaseLLMProvider):
    MODELS = [
        ("gemini-3-pro-preview", "Gemini 3 Pro (Preview)"),
        ("gemini-3-flash-preview", "Gemini 3 Flash (Preview)"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite"),
    ]

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Gemini"

    def get_models(self) -> List[Tuple[str, str]]:
        return self.MODELS

    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None) -> List[str]:
        cmd = ["gemini"]
        if model:
            cmd.extend(["--model", model])
        cmd.append("--yolo")
        return cmd


LLMProviderRegistry.register(GeminiProvider())
