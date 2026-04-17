"""Base LLM provider interface and registry."""

import json
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Tuple


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
                      working_directory: Optional[str] = None,
                      session_id: Optional[str] = None) -> List[str]:
        """Build the subprocess command list. Prompt is sent via stdin."""

    @property
    def uses_stdin(self) -> bool:
        return True

    def get_stdin_prompt(self, prompt: str) -> str:
        return prompt

    def supports_session_resume(self, model: Optional[str] = None) -> bool:
        _ = model
        return False

    def uses_structured_output(self, model: Optional[str] = None) -> bool:
        _ = model
        return False

    def parse_structured_output(self, lines: Iterable[str]) -> Tuple[str, str]:
        text_lines: List[str] = []
        session_id = ""
        for line in lines:
            text = str(line).strip()
            if not text:
                continue
            text_lines.append(text)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            candidate = self._find_session_id(payload)
            if candidate:
                session_id = candidate
        return "\n".join(text_lines), session_id

    def _find_session_id(self, payload: object) -> str:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in {"session_id", "thread_id"} and isinstance(value, str) and value.strip():
                    return value.strip()
                nested = self._find_session_id(value)
                if nested:
                    return nested
        elif isinstance(payload, list):
            for item in payload:
                nested = self._find_session_id(item)
                if nested:
                    return nested
        return ""

    def _flatten_text(self, payload: object) -> List[str]:
        flattened: List[str] = []
        if isinstance(payload, str):
            flattened.append(payload)
        elif isinstance(payload, dict):
            for value in payload.values():
                flattened.extend(self._flatten_text(value))
        elif isinstance(payload, list):
            for item in payload:
                flattened.extend(self._flatten_text(item))
        return flattened


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
