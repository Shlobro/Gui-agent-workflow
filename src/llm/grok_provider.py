"""Grok Build CLI provider (xAI)."""

import json
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from .base_provider import (
    BaseLLMProvider,
    LLMProviderRegistry,
    ModelEntry,
    effort_variants,
)


class GrokProvider(BaseLLMProvider):
    ENTRIES = [
        ModelEntry(
            model_id="grok-4.6",
            label="Grok 4.6",
            variants=effort_variants("low", "medium", "high", "xhigh"),
            default_variant_id="medium",
        ),
        ModelEntry(
            model_id="grok-4.5",
            label="Grok 4.5",
            variants=effort_variants("low", "medium", "high"),
            default_variant_id="medium",
        ),
    ]

    @property
    def name(self) -> str:
        return "grok"

    @property
    def display_name(self) -> str:
        return "Grok"

    def get_model_entries(self) -> List[ModelEntry]:
        return self.ENTRIES

    @property
    def uses_stdin(self) -> bool:
        return False

    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None,
                      session_id: Optional[str] = None) -> List[str]:
        cmd = ["grok", "--always-approve", "--no-alt-screen", "--no-auto-update"]

        normalized_wd: Optional[str] = None
        if working_directory and str(working_directory).strip():
            candidate = Path(working_directory)
            if candidate.exists() and candidate.is_dir():
                normalized_wd = str(candidate)
        if normalized_wd:
            cmd.extend(["--cwd", normalized_wd])

        actual_model = model
        effort = None
        if model and ":" in model:
            actual_model, effort = model.split(":", 1)

        if actual_model and actual_model.strip():
            cmd.extend(["--model", actual_model.strip()])
        if effort and effort.strip():
            cmd.extend(["--effort", effort.strip()])

        if session_id and session_id.strip():
            cmd.extend(["--resume", session_id.strip()])

        cmd.extend(["--output-format", "json"])
        cmd.extend(["-p", prompt])
        return cmd

    def supports_session_resume(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def uses_structured_output(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def parse_structured_output(self, lines: Iterable[str]) -> Tuple[str, str]:
        decoder = json.JSONDecoder()
        blob = "\n".join(str(line).rstrip() for line in lines if str(line).strip())
        text_candidates: List[str] = []
        session_id = ""
        index = 0
        while index < len(blob):
            char = blob[index]
            if char != "{":
                index += 1
                continue
            try:
                payload, end = decoder.raw_decode(blob, index)
            except json.JSONDecodeError:
                index += 1
                continue
            index = max(end, index + 1)
            if not isinstance(payload, dict):
                continue
            candidate = payload.get("sessionId")
            if isinstance(candidate, str) and candidate.strip():
                session_id = candidate.strip()
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                text_candidates.append(text.strip())
        if text_candidates:
            return text_candidates[-1], session_id
        return "", session_id


LLMProviderRegistry.register(GrokProvider())
