"""Claude CLI provider."""

import json
from typing import Iterable, List, Optional, Tuple
from .base_provider import (
    BaseLLMProvider,
    LLMProviderRegistry,
    ModelEntry,
    effort_variants,
)


THINKING_REQUIRED_EFFORTS = frozenset({"xhigh", "max"})
ALWAYS_THINKING_SETTINGS_JSON = '{"alwaysThinkingEnabled": true}'


class ClaudeProvider(BaseLLMProvider):
    ENTRIES = [
        ModelEntry(
            model_id="claude-opus-5",
            label="Claude Opus 5",
            variants=effort_variants("low", "medium", "high", "xhigh", "max"),
            default_variant_id="high",
        ),
        ModelEntry(
            model_id="claude-sonnet-5",
            label="Claude Sonnet 5",
            variants=effort_variants("low", "medium", "high", "xhigh"),
            default_variant_id="medium",
        ),
    ]

    @property
    def name(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Claude"

    def get_model_entries(self) -> List[ModelEntry]:
        return self.ENTRIES

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
        if effort in THINKING_REQUIRED_EFFORTS:
            cmd.extend(["--settings", ALWAYS_THINKING_SETTINGS_JSON])
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
