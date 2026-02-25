"""Base LLM provider interface and registry."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class BaseLLMProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider (e.g. 'claude')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g. 'Claude')."""

    @abstractmethod
    def get_models(self) -> List[Tuple[str, str]]:
        """Return list of (model_id, display_name) tuples."""

    @abstractmethod
    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None) -> List[str]:
        """Build the subprocess command list. Prompt is sent via stdin."""

    @property
    def uses_stdin(self) -> bool:
        return True

    def get_stdin_prompt(self, prompt: str) -> str:
        return prompt


class LLMProviderRegistry:
    _providers: Dict[str, "BaseLLMProvider"] = {}

    @classmethod
    def register(cls, provider: "BaseLLMProvider") -> None:
        cls._providers[provider.name] = provider

    @classmethod
    def get(cls, name: str) -> "BaseLLMProvider":
        return cls._providers[name]

    @classmethod
    def all(cls) -> List["BaseLLMProvider"]:
        return list(cls._providers.values())
