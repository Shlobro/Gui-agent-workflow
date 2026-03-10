"""Prompt injection template storage and assembly helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

MAX_TEMPLATE_NAME_CHARS = 80
MAX_TEMPLATE_CONTENT_CHARS = 4000
MAX_ONE_OFF_INJECTION_CHARS = 4000

BUILTIN_RUNTIME_CONTEXT_TEMPLATE_ID = "runtime_context_headless"


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    name: str
    content: str
    built_in: bool = False


@dataclass(frozen=True)
class PromptInjectionConfig:
    templates: tuple[PromptTemplate, ...]
    default_enabled_template_ids: tuple[str, ...]


@dataclass(frozen=True)
class PromptInjectionRunOptions:
    enabled_template_ids: tuple[str, ...]
    one_off_text: str = ""


_BUILTIN_TEMPLATES: tuple[PromptTemplate, ...] = (
    PromptTemplate(
        template_id=BUILTIN_RUNTIME_CONTEXT_TEMPLATE_ID,
        name="Runtime Context (Headless)",
        content=(
            "Execution context: this LLM run is headless. Do not ask the user "
            "follow-up questions or wait for interactive input.\n"
            "Each run starts as a fresh instance with no memory from prior runs."
        ),
        built_in=True,
    ),
)
_BUILTIN_TEMPLATE_IDS = {template.template_id for template in _BUILTIN_TEMPLATES}
_DEFAULT_CONFIG = PromptInjectionConfig(
    templates=_BUILTIN_TEMPLATES,
    default_enabled_template_ids=(BUILTIN_RUNTIME_CONTEXT_TEMPLATE_ID,),
)
_CONFIG_FILENAME = ".prompt_injections.json"


def _normalize_name(name: str) -> str:
    value = " ".join((name or "").split()).strip()
    if not value:
        raise ValueError("Template name cannot be empty.")
    if len(value) > MAX_TEMPLATE_NAME_CHARS:
        raise ValueError(f"Template name must be {MAX_TEMPLATE_NAME_CHARS} characters or fewer.")
    return value


def _normalize_content(content: str) -> str:
    value = (content or "").strip()
    if not value:
        raise ValueError("Template content cannot be empty.")
    if len(value) > MAX_TEMPLATE_CONTENT_CHARS:
        raise ValueError(
            f"Template content must be {MAX_TEMPLATE_CONTENT_CHARS} characters or fewer."
        )
    return value


def normalize_one_off_text(text: str) -> str:
    value = (text or "").strip()
    if len(value) > MAX_ONE_OFF_INJECTION_CHARS:
        raise ValueError(
            f"One-off injection must be {MAX_ONE_OFF_INJECTION_CHARS} characters or fewer."
        )
    return value


def create_user_template(name: str, content: str, template_id: str | None = None) -> PromptTemplate:
    normalized_id = (template_id or "").strip() or str(uuid4())
    if normalized_id in _BUILTIN_TEMPLATE_IDS:
        raise ValueError("User template id conflicts with a built-in template id.")
    return PromptTemplate(
        template_id=normalized_id,
        name=_normalize_name(name),
        content=_normalize_content(content),
        built_in=False,
    )


def unique_existing_template_ids(
    config: PromptInjectionConfig, template_ids: Iterable[str]
) -> tuple[str, ...]:
    existing_ids = {template.template_id for template in config.templates}
    ordered_unique: list[str] = []
    seen: set[str] = set()
    for template_id in template_ids:
        normalized = str(template_id).strip()
        if not normalized or normalized in seen:
            continue
        if normalized not in existing_ids:
            continue
        seen.add(normalized)
        ordered_unique.append(normalized)
    return tuple(ordered_unique)


def resolve_template_contents(
    config: PromptInjectionConfig, enabled_template_ids: Sequence[str]
) -> list[str]:
    enabled = set(unique_existing_template_ids(config, enabled_template_ids))
    return [
        template.content
        for template in config.templates
        if template.template_id in enabled and template.content.strip()
    ]


def compose_prompt(
    base_prompt: str, template_contents: Sequence[str], one_off_text: str = ""
) -> str:
    normalized_base = base_prompt or ""
    normalized_templates = [section.strip() for section in template_contents if section.strip()]
    normalized_one_off = normalize_one_off_text(one_off_text)
    if not normalized_templates and not normalized_one_off:
        return normalized_base

    injection_sections = [
        f"[Template {idx}]\n{section}"
        for idx, section in enumerate(normalized_templates, start=1)
    ]
    if normalized_one_off:
        injection_sections.append(f"[One-Off Injection]\n{normalized_one_off}")
    injected_context = "[Injected Context]\n" + "\n\n".join(injection_sections)
    if normalized_base.strip():
        return normalized_base.rstrip() + "\n\n" + injected_context
    return injected_context


def normalize_run_options(
    config: PromptInjectionConfig, run_options: PromptInjectionRunOptions | None
) -> PromptInjectionRunOptions:
    if run_options is None:
        return PromptInjectionRunOptions(
            enabled_template_ids=unique_existing_template_ids(
                config, config.default_enabled_template_ids
            ),
            one_off_text="",
        )
    return PromptInjectionRunOptions(
        enabled_template_ids=unique_existing_template_ids(
            config, run_options.enabled_template_ids
        ),
        one_off_text=normalize_one_off_text(run_options.one_off_text),
    )


class PromptInjectionStore:
    """Persistent storage for prompt templates and default enabled templates."""

    def __init__(self, path: Path | None = None):
        self._path = path or (Path(__file__).resolve().parents[2] / _CONFIG_FILENAME)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> PromptInjectionConfig:
        if not self._path.exists():
            return _DEFAULT_CONFIG
        try:
            with self._path.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except (OSError, json.JSONDecodeError, TypeError):
            return _DEFAULT_CONFIG
        if not isinstance(payload, dict):
            return _DEFAULT_CONFIG

        user_templates = self._load_user_templates(payload.get("templates", []))
        all_templates = _BUILTIN_TEMPLATES + tuple(user_templates)

        if "default_enabled_template_ids" in payload:
            raw_default_ids = payload.get("default_enabled_template_ids", [])
            if not isinstance(raw_default_ids, list):
                raw_default_ids = []
            default_ids = unique_existing_template_ids(
                PromptInjectionConfig(all_templates, ()),
                [str(item) for item in raw_default_ids],
            )
        else:
            default_ids = (BUILTIN_RUNTIME_CONTEXT_TEMPLATE_ID,)

        return PromptInjectionConfig(
            templates=all_templates,
            default_enabled_template_ids=default_ids,
        )

    def save(self, config: PromptInjectionConfig) -> None:
        normalized = self._normalize_config(config)
        payload = {
            "version": 1,
            "templates": [
                {
                    "id": template.template_id,
                    "name": template.name,
                    "content": template.content,
                }
                for template in normalized.templates
                if not template.built_in
            ],
            "default_enabled_template_ids": list(normalized.default_enabled_template_ids),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, indent=2)

    def _load_user_templates(self, raw_templates: object) -> list[PromptTemplate]:
        if not isinstance(raw_templates, list):
            return []
        loaded: list[PromptTemplate] = []
        used_ids = set(_BUILTIN_TEMPLATE_IDS)
        used_names = {template.name.casefold() for template in _BUILTIN_TEMPLATES}
        for item in raw_templates:
            if not isinstance(item, dict):
                continue
            template_id = str(item.get("id", "")).strip()
            if not template_id or template_id in used_ids:
                continue
            raw_name = item.get("name", "")
            raw_content = item.get("content", "")
            if not isinstance(raw_name, str) or not isinstance(raw_content, str):
                continue
            try:
                normalized_name = _normalize_name(raw_name)
                normalized_content = _normalize_content(raw_content)
            except ValueError:
                continue
            name_key = normalized_name.casefold()
            if name_key in used_names:
                continue
            used_ids.add(template_id)
            used_names.add(name_key)
            loaded.append(
                PromptTemplate(
                    template_id=template_id,
                    name=normalized_name,
                    content=normalized_content,
                    built_in=False,
                )
            )
        return loaded

    def _normalize_config(self, config: PromptInjectionConfig) -> PromptInjectionConfig:
        user_templates: list[PromptTemplate] = []
        seen_ids = set(_BUILTIN_TEMPLATE_IDS)
        seen_names = {template.name.casefold() for template in _BUILTIN_TEMPLATES}
        for template in config.templates:
            if template.template_id in _BUILTIN_TEMPLATE_IDS:
                continue
            try:
                normalized_name = _normalize_name(template.name)
                normalized_content = _normalize_content(template.content)
            except ValueError:
                continue
            template_id = (template.template_id or "").strip()
            if not template_id:
                template_id = str(uuid4())
            if template_id in seen_ids:
                template_id = str(uuid4())
            name_key = normalized_name.casefold()
            if name_key in seen_names:
                continue
            seen_ids.add(template_id)
            seen_names.add(name_key)
            user_templates.append(
                PromptTemplate(
                    template_id=template_id,
                    name=normalized_name,
                    content=normalized_content,
                    built_in=False,
                )
            )
        templates = _BUILTIN_TEMPLATES + tuple(user_templates)
        normalized_ids = unique_existing_template_ids(
            PromptInjectionConfig(templates, ()),
            config.default_enabled_template_ids,
        )
        return PromptInjectionConfig(templates=templates, default_enabled_template_ids=normalized_ids)
