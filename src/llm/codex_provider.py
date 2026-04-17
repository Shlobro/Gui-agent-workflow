"""Codex CLI provider."""

import json
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from .base_provider import BaseLLMProvider, LLMProviderRegistry


class CodexProvider(BaseLLMProvider):
    MODELS = [
        ("gpt-5.4", "GPT-5.4 (Medium)"),
        ("gpt-5.4:low", "GPT-5.4 (Low)"),
        ("gpt-5.4:high", "GPT-5.4 (High)"),
        ("gpt-5.4:xhigh", "GPT-5.4 (Ultra High)"),
        ("gpt-5.3-codex", "GPT-5.3 Codex (Medium)"),
        ("gpt-5.3-codex:low", "GPT-5.3 Codex (Low)"),
        ("gpt-5.3-codex:high", "GPT-5.3 Codex (High)"),
        ("gpt-5.3-codex:xhigh", "GPT-5.3 Codex (Ultra High)"),
    ]

    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex"

    def get_models(self) -> List[Tuple[str, str]]:
        return self.MODELS

    @property
    def uses_stdin(self) -> bool:
        return False

    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None,
                      session_id: Optional[str] = None) -> List[str]:
        cmd = ["codex", "exec"]
        cmd.extend(["--skip-git-repo-check", "--full-auto", "--json"])

        normalized_wd: Optional[str] = None
        if working_directory and str(working_directory).strip():
            candidate = Path(working_directory)
            if candidate.exists() and candidate.is_dir():
                normalized_wd = str(candidate)
        if normalized_wd:
            cmd.extend(["-C", normalized_wd])

        actual_model = model
        reasoning_effort = None
        if model and ":" in model:
            actual_model, reasoning_effort = model.split(":", 1)

        if actual_model:
            cmd.extend(["--model", actual_model])
        if reasoning_effort:
            cmd.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])

        if session_id:
            cmd.extend(["resume", session_id, prompt])
        else:
            cmd.append(prompt)
        return cmd

    def supports_session_resume(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def uses_structured_output(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def parse_structured_output(self, lines: Iterable[str]) -> Tuple[str, str]:
        session_id = ""
        final_messages: List[str] = []
        fallback_messages: List[str] = []
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
            if not isinstance(payload, dict):
                continue
            event_type = str(payload.get("type", "")).strip().lower()
            joined_output = self._extract_codex_message(payload)
            if not joined_output:
                continue
            if event_type in {"result", "message", "final_message", "assistant_message"}:
                final_messages.append(joined_output)
            elif "assistant" in event_type or "completed" in event_type:
                fallback_messages.append(joined_output)
        if final_messages:
            return final_messages[-1], session_id
        if fallback_messages:
            return fallback_messages[-1], session_id
        return "", session_id

    def _extract_codex_message(self, payload: dict) -> str:
        item = payload.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type", "")).strip().lower()
            if item_type in {"agent_message", "assistant_message", "message"}:
                joined = "\n".join(
                    part.strip()
                    for part in self._flatten_text(
                        item.get("text")
                        if "text" in item
                        else item.get("content", item.get("output", item.get("result")))
                    )
                    if part and part.strip()
                ).strip()
                if joined:
                    return joined
        for key in ("last_message", "final_message", "message", "result", "content", "output"):
            joined = "\n".join(
                part.strip() for part in self._flatten_text(payload.get(key)) if part and part.strip()
            ).strip()
            if joined:
                return joined
        return ""


LLMProviderRegistry.register(CodexProvider())
