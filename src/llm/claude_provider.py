"""Claude CLI provider."""

import json
from typing import Iterable, List, Optional, Tuple
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
                      working_directory: Optional[str] = None,
                      session_id: Optional[str] = None) -> List[str]:
        _ = working_directory
        cmd = ["claude", "--dangerously-skip-permissions", "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.append("-p")
        return cmd

    def supports_session_resume(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def uses_structured_output(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def parse_structured_output(self, lines: Iterable[str]) -> Tuple[str, str]:
        session_id = ""
        text_candidates: List[str] = []
        for line in lines:
            text = str(line).strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            candidate = self._find_session_id(payload)
            if candidate:
                session_id = candidate
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, str) and result.strip():
                text_candidates.append(result.strip())
                continue
            message = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(message, str) and message.strip():
                text_candidates.append(message.strip())
                continue
            if isinstance(payload, dict):
                flattened = self._flatten_text(payload.get("content"))
                joined = "\n".join(part.strip() for part in flattened if part and part.strip()).strip()
                if joined:
                    text_candidates.append(joined)
        if text_candidates:
            return text_candidates[-1], session_id
        return "", session_id


LLMProviderRegistry.register(ClaudeProvider())
