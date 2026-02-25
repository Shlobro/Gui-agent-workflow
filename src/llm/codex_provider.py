"""Codex CLI provider."""

from pathlib import Path
from typing import List, Optional, Tuple
from .base_provider import BaseLLMProvider, LLMProviderRegistry


class CodexProvider(BaseLLMProvider):
    OUTPUT_FILENAME = ".codex_last_message.txt"
    MODELS = [
        ("gpt-5.3-codex", "GPT-5.3 Codex (Medium)"),
        ("gpt-5.3-codex:low", "GPT-5.3 Codex (Low)"),
        ("gpt-5.3-codex:high", "GPT-5.3 Codex (High)"),
        ("gpt-5.3-codex:xhigh", "GPT-5.3 Codex (Ultra High)"),
        ("gpt-5.2-codex", "GPT-5.2 Codex (Medium)"),
        ("gpt-5.2-codex:low", "GPT-5.2 Codex (Low)"),
        ("gpt-5.2-codex:high", "GPT-5.2 Codex (High)"),
        ("gpt-5.2-codex:xhigh", "GPT-5.2 Codex (Ultra High)"),
        ("gpt-5.1-codex-max", "GPT-5.1 Codex Max"),
        ("gpt-5.1-codex-mini", "GPT-5.1 Codex Mini"),
        ("gpt-5.2", "GPT-5.2"),
    ]

    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex"

    def get_models(self) -> List[Tuple[str, str]]:
        return self.MODELS

    def build_command(self, prompt: str, model: Optional[str] = None,
                      working_directory: Optional[str] = None) -> List[str]:
        cmd = ["codex", "exec", "--skip-git-repo-check", "--full-auto"]

        normalized_wd: Optional[str] = None
        if working_directory and str(working_directory).strip():
            candidate = Path(working_directory)
            if candidate.exists() and candidate.is_dir():
                normalized_wd = str(candidate)
        if normalized_wd:
            cmd.extend(["--cd", normalized_wd])
            cmd.extend(["--add-dir", normalized_wd])

        actual_model = model
        reasoning_effort = None
        if model and ":" in model:
            actual_model, reasoning_effort = model.split(":", 1)

        if normalized_wd:
            output_path = str(Path(normalized_wd) / self.OUTPUT_FILENAME)
            cmd.extend(["--output-last-message", output_path])

        if actual_model:
            cmd.extend(["--model", actual_model])
        if reasoning_effort:
            cmd.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])

        cmd.append("-")
        return cmd


LLMProviderRegistry.register(CodexProvider())
