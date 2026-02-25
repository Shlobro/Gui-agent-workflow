"""Claude CLI provider."""

from typing import List, Optional, Tuple
from .base_provider import BaseLLMProvider, LLMProviderRegistry


class ClaudeProvider(BaseLLMProvider):
    MODELS = [
        ("claude-opus-4-6", "Claude Opus 4.6"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ]

    @property
    def name(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Claude"

    def get_models(self) -> List[Tuple[str, str]]:
        return self.MODELS

    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None) -> List[str]:
        cmd = ["claude", "--dangerously-skip-permissions"]
        if model:
            cmd.extend(["--model", model])
        cmd.append("-p")
        return cmd


LLMProviderRegistry.register(ClaudeProvider())
