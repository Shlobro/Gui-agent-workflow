"""Codex CLI provider."""

import json
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from .base_provider import (
    BaseLLMProvider,
    LLMProviderRegistry,
    ModelEntry,
    effort_variants,
)


class CodexProvider(BaseLLMProvider):
    ENTRIES = [
        ModelEntry(
            model_id="gpt-5.6-sol",
            label="GPT-5.6 Sol",
            variants=effort_variants("low", "medium", "high", "xhigh", "max", "ultra"),
            default_variant_id="low",
        ),
        ModelEntry(
            model_id="gpt-5.6-terra",
            label="GPT-5.6 Terra",
            variants=effort_variants("low", "medium", "high", "xhigh", "max", "ultra"),
            default_variant_id="medium",
        ),
        ModelEntry(
            model_id="gpt-5.6-luna",
            label="GPT-5.6 Luna",
            variants=effort_variants("low", "medium", "high", "xhigh", "max"),
            default_variant_id="medium",
        ),
    ]

    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex"

    def get_model_entries(self) -> List[ModelEntry]:
        return self.ENTRIES

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

    def supports_profiles(self) -> bool:
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
        text = str(line).strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []

        event_type = str(payload.get("type", "")).strip().lower()
        item = payload.get("item")
        lines: List[str] = []

        if event_type == "thread.started":
            thread_id = self._find_session_id(payload)
            if thread_id:
                lines.append(f"[Thread] Started {thread_id}")
            return lines

        if event_type == "error":
            message = self._extract_progress_message(payload)
            if message:
                lines.append(f"[Codex] {message}")
            return lines

        if isinstance(item, dict):
            item_type = str(item.get("type", "")).strip().lower()
            if item_type in {"agent_message", "assistant_message", "message"}:
                return []

            if "started" in event_type:
                label = self._describe_progress_item(item)
                if label:
                    lines.append(f"[Progress] Started {label}")
                return lines

            if "completed" in event_type:
                label = self._describe_progress_item(item)
                if label:
                    lines.append(f"[Progress] Finished {label}")
                return lines

            if item_type:
                label = self._describe_progress_item(item)
                if label:
                    lines.append(f"[Progress] {label}")
                return lines

        if event_type in {"turn.started", "step.started"}:
            lines.append("[Progress] Working...")
            return lines

        if event_type in {"turn.completed", "step.completed", "result"}:
            return []

        message = self._extract_progress_message(payload)
        if message:
            lines.append(f"[Codex] {message}")
        return lines

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

    def _describe_progress_item(self, item: dict) -> str:
        item_type = str(item.get("type", "")).strip().lower()
        tool_name = self._first_non_empty_text(
            item.get("tool_name"),
            item.get("name"),
            item.get("title"),
            item.get("command"),
            item.get("action"),
            item.get("kind"),
            item.get("description"),
            item.get("path"),
            item.get("file_path"),
            item.get("query"),
            item.get("pattern"),
            item.get("input"),
            item.get("arguments"),
            item.get("params"),
            item.get("call"),
        )
        item_label = item_type.replace("_", " ").strip() if item_type else "step"
        if tool_name:
            tool_name = " ".join(tool_name.split())
            return f"{item_label}: {tool_name}"
        return item_label

    def _extract_progress_message(self, payload: dict) -> str:
        for key in ("message", "detail", "status", "summary", "result"):
            message = self._first_non_empty_text(payload.get(key))
            if message:
                return message
        return ""

    def _first_non_empty_text(self, *values: object) -> str:
        for value in values:
            text = self._value_to_text(value)
            if text:
                return text
        return ""

    def _value_to_text(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            for item in value:
                text = self._value_to_text(item)
                if text:
                    return text
            return ""
        if isinstance(value, dict):
            preferred_keys = (
                "name",
                "tool_name",
                "command",
                "title",
                "action",
                "kind",
                "description",
                "path",
                "file_path",
                "query",
                "pattern",
                "text",
                "input",
                "arguments",
                "params",
            )
            for key in preferred_keys:
                text = self._value_to_text(value.get(key))
                if text:
                    return text
            flattened = [
                part.strip()
                for part in self._flatten_text(value)
                if isinstance(part, str) and part.strip()
            ]
            if flattened:
                return flattened[0]
        return ""


LLMProviderRegistry.register(CodexProvider())
