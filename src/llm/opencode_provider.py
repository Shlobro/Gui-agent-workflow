"""OpenCode CLI provider (free OpenCode Zen models)."""

import json
import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from .base_provider import (
    BaseLLMProvider,
    LLMProviderRegistry,
    ModelEntry,
)


_ZEN_PROVIDER_PREFIX = "opencode"
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


class OpenCodeProvider(BaseLLMProvider):
    ENTRIES = [
        ModelEntry(model_id="x-preview-f-free", label="Ox Alpha Free"),
        ModelEntry(model_id="mimo-v2.5-free", label="MiMo-V2.5 Free"),
        ModelEntry(model_id="hy3-free", label="Hy3 Free"),
        ModelEntry(model_id="nemotron-3-ultra-free", label="Nemotron 3 Ultra Free"),
        ModelEntry(model_id="nemotron-3.5-lightning-free", label="Nemotron 3.5 Lightning Free"),
        ModelEntry(model_id="muse-spark-1.2-contributor-free", label="Muse Spark 1.2 Contributor Free"),
    ]

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def display_name(self) -> str:
        return "OpenCode"

    def get_model_entries(self) -> List[ModelEntry]:
        return self.ENTRIES

    @property
    def uses_stdin(self) -> bool:
        return False

    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None,
                      session_id: Optional[str] = None) -> List[str]:
        cmd = ["opencode", "run", "--format", "json", "--auto"]

        normalized_wd: Optional[str] = None
        if working_directory and str(working_directory).strip():
            candidate = Path(working_directory)
            if candidate.exists() and candidate.is_dir():
                normalized_wd = str(candidate)
        if normalized_wd:
            cmd.extend(["--dir", normalized_wd])

        if model and model.strip():
            cmd.extend(["--model", f"{_ZEN_PROVIDER_PREFIX}/{model.strip()}"])

        if session_id and session_id.strip():
            cmd.extend(["--session", session_id.strip()])

        cmd.append(prompt)
        return cmd

    def supports_session_resume(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def uses_structured_output(self, model: Optional[str] = None) -> bool:
        _ = model
        return True

    def structured_output_progress_lines(
        self,
        line: str,
        model: Optional[str] = None,
    ) -> List[str]:
        _ = model
        text = _strip_ansi(str(line)).strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return [f"[OpenCode] {text}"]
        if not isinstance(payload, dict):
            return []

        event_type = str(payload.get("type", "")).strip().lower()
        part = payload.get("part")

        if event_type == "error":
            message = self._extract_error_message(payload)
            if message:
                return [f"[OpenCode] {message}"]
            return []

        if event_type == "tool_use" and isinstance(part, dict):
            tool_name = str(part.get("tool", "")).strip() or "tool"
            state = part.get("state")
            status = ""
            title = ""
            error_text = ""
            if isinstance(state, dict):
                status = str(state.get("status", "")).strip().lower()
                title = self._first_non_empty_text(
                    state.get("title"),
                    state.get("description"),
                )
                error_text = self._first_non_empty_text(state.get("error"))
            if status == "error":
                detail = error_text or title or tool_name
                return [f"[OpenCode] Tool '{tool_name}' failed: {detail}"]
            label = f"{tool_name}: {title}" if title else tool_name
            if status in {"pending", "running", ""}:
                return [f"[Progress] Started {label}"]
            return [f"[Progress] Finished {label}"]

        return []

    def parse_structured_output(self, lines: Iterable[str]) -> Tuple[str, str]:
        session_id = ""
        text_parts: List[str] = []
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
            part = payload.get("part")
            if isinstance(part, dict) and str(part.get("type", "")).strip().lower() == "text":
                body = part.get("text")
                if isinstance(body, str) and body.strip():
                    text_parts.append(body.strip())
        return "\n".join(text_parts), session_id

    def _find_session_id(self, payload: object) -> str:
        if isinstance(payload, dict):
            for key in ("sessionID", "sessionId"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return super()._find_session_id(payload)

    def _extract_error_message(self, payload: dict) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            nested = error.get("message") or error.get("name")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return self._first_non_empty_text(
            payload.get("message"),
            payload.get("name"),
            error,
        )

    def _first_non_empty_text(self, *values: object) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float, bool)):
                return str(value)
            if isinstance(value, list):
                flattened = [
                    part.strip()
                    for part in self._flatten_text(value)
                    if isinstance(part, str) and part.strip()
                ]
                if flattened:
                    return flattened[0]
        return ""


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_PATTERN.sub("", text)


LLMProviderRegistry.register(OpenCodeProvider())
