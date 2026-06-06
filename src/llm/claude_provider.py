"""Claude CLI provider."""

import json
from typing import Iterable, List, Optional, Tuple
from .base_provider import BaseLLMProvider, LLMProviderRegistry


class ClaudeProvider(BaseLLMProvider):
    MODELS = [
        ("claude-opus-4-8:low", "Claude Opus 4.8 (Low)"),
        ("claude-opus-4-8:medium", "Claude Opus 4.8 (Medium)"),
        ("claude-opus-4-8:high", "Claude Opus 4.8 (High)"),
        ("claude-opus-4-8:xhigh", "Claude Opus 4.8 (Ultra High)"),
        ("claude-opus-4-8:max", "Claude Opus 4.8 (Max)"),
        ("claude-sonnet-4-6:low", "Claude Sonnet 4.6 (Low)"),
        ("claude-sonnet-4-6:medium", "Claude Sonnet 4.6 (Medium)"),
        ("claude-sonnet-4-6:high", "Claude Sonnet 4.6 (High)"),
        ("claude-sonnet-4-6:max", "Claude Sonnet 4.6 (Max)"),
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
        actual_model = model
        effort = None
        if model and ":" in model:
            actual_model, effort = model.split(":", 1)

        if actual_model:
            cmd.extend(["--model", actual_model])
        if effort:
            cmd.extend(["--effort", effort])
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.append("-p")
        return cmd

    def supports_session_resume(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def supports_profiles(self) -> bool:
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
