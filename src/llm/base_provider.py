"""Base LLM provider interface and registry."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ModelVariant:
    """One selectable variant (e.g. reasoning-effort level) of a model."""

    id: str
    label: str


EFFORT_VARIANT_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Ultra High",
    "max": "Max",
    "ultra": "Ultra",
}


def effort_variants(*effort_ids: str) -> Tuple[ModelVariant, ...]:
    """Build reasoning-effort variants from canonical effort ids."""
    return tuple(ModelVariant(effort, EFFORT_VARIANT_LABELS[effort]) for effort in effort_ids)


@dataclass(frozen=True)
class ModelEntry:
    """One selectable model and its available variants.

    ``variants`` is empty for models with nothing to choose (e.g. free
    preview models). ``default_variant_id`` picks the preselected variant;
    when empty the first variant is the default.
    """

    model_id: str
    label: str
    variants: Tuple[ModelVariant, ...] = ()
    default_variant_id: str = ""

    def default_variant(self) -> Optional[ModelVariant]:
        if not self.variants:
            return None
        for variant in self.variants:
            if variant.id == self.default_variant_id:
                return variant
        return self.variants[0]

    def resolve_variant(self, variant_id: str) -> Optional[ModelVariant]:
        for variant in self.variants:
            if variant.id == variant_id:
                return variant
        return None


def split_model_variant(model_id: str) -> Tuple[str, str]:
    """Split a stored id like ``claude-opus-5:high`` into (base, variant)."""
    text = str(model_id or "")
    if ":" in text:
        base, variant = text.split(":", 1)
        return base, variant
    return text, ""


def compose_model_variant(base_model_id: str, variant_id: str) -> str:
    base = str(base_model_id or "").strip()
    variant = str(variant_id or "").strip()
    if base and variant:
        return f"{base}:{variant}"
    return base


def normalize_model_id(model_id: Optional[str]) -> Optional[str]:
    """Map saved legacy model ids onto the currently registered catalog."""
    if model_id is None:
        return None
    return LEGACY_MODEL_ID_ALIASES.get(model_id, model_id)


def _build_legacy_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {}

    opus_sources = (
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-0",
    )
    for source in opus_sources:
        for effort in ("low", "medium", "high", "xhigh", "max"):
            aliases[f"{source}:{effort}"] = f"claude-opus-5:{effort}"
        aliases[source] = "claude-opus-5:high"

    sonnet_efforts = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "max": "xhigh",
    }
    sonnet_sources = (
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-sonnet-4-0",
    )
    for source in sonnet_sources:
        for effort, target in sonnet_efforts.items():
            aliases[f"{source}:{effort}"] = f"claude-sonnet-5:{target}"
        aliases[source] = "claude-sonnet-5:medium"

    haiku_sources = (
        "claude-haiku-4-5-20251001",
        "claude-3-5-haiku-latest",
    )
    for source in haiku_sources:
        aliases[source] = "claude-sonnet-5:medium"

    codex_rules = (
        ("gpt-5.5", {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}),
        ("gpt-5.4", {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}),
        ("gpt-5.3-codex", {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}),
    )
    codex_targets = {
        "gpt-5.5": "gpt-5.6-terra",
        "gpt-5.4": "gpt-5.6-terra",
        "gpt-5.3-codex": "gpt-5.6-sol",
    }
    defaults = {
        "gpt-5.5": "gpt-5.6-terra:medium",
        "gpt-5.4": "gpt-5.6-terra:medium",
        "gpt-5.3-codex": "gpt-5.6-sol:low",
    }
    for source, efforts in codex_rules:
        target_base = codex_targets[source]
        for effort in efforts:
            aliases[f"{source}:{effort}"] = f"{target_base}:{effort}"
        aliases[source] = defaults[source]

    aliases["grok-4.5:xhigh"] = "grok-4.5:high"

    return aliases


LEGACY_MODEL_ID_ALIASES: Dict[str, str] = _build_legacy_aliases()


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
    def get_model_entries(self) -> List[ModelEntry]:
        """Return the selectable catalog as structured entries."""

    def get_models(self) -> List[Tuple[str, str]]:
        """Flatten the catalog into (full_model_id, label) tuples.

        Entries with variants expand to one tuple per
        ``<model_id>:<variant_id>`` combination; entries without variants
        appear once under their bare id.
        """
        models: List[Tuple[str, str]] = []
        for entry in self.get_model_entries():
            if entry.variants:
                for variant in entry.variants:
                    full_id = compose_model_variant(entry.model_id, variant.id)
                    models.append((full_id, f"{entry.label} ({variant.label})"))
            else:
                models.append((entry.model_id, entry.label))
        return models

    def find_model_entry(self, model_id: Optional[str]) -> Optional[Tuple[ModelEntry, Optional[ModelVariant]]]:
        """Resolve a stored full id onto its catalog entry and variant."""
        normalized = normalize_model_id(model_id)
        if not normalized:
            return None
        base, variant_id = split_model_variant(normalized)
        for entry in self.get_model_entries():
            if entry.model_id != base:
                continue
            if entry.variants:
                return entry, entry.resolve_variant(variant_id) or entry.default_variant()
            return entry, None
        return None

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

    def supports_profiles(self) -> bool:
        """Whether this provider exposes selectable account profiles.

        Profiles are config-home directories selected via an environment
        variable; see ``src/llm/profiles.py``.
        """
        return False

    def uses_structured_output(self, model: Optional[str] = None) -> bool:
        _ = model
        return False

    def structured_output_progress_lines(
        self,
        line: str,
        model: Optional[str] = None,
    ) -> List[str]:
        _ = line, model
        return []

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
