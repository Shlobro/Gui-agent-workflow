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

POSITION_PREPEND = "prepend"
POSITION_APPEND = "append"
VALID_POSITIONS = (POSITION_PREPEND, POSITION_APPEND)

BUILTIN_RUNTIME_CONTEXT_TEMPLATE_ID = "runtime_context_headless"


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    name: str
    content: str
    built_in: bool = False
    placement: str = POSITION_APPEND


@dataclass(frozen=True)
class PromptInjectionConfig:
    templates: tuple[PromptTemplate, ...]
    default_enabled_template_ids: tuple[str, ...]


@dataclass(frozen=True)
class PromptInjectionRunOptions:
    enabled_template_ids: tuple[str, ...]
    one_off_text: str = ""
    one_off_placement: str = POSITION_APPEND


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
        placement=POSITION_APPEND,
    ),
)
_BUILTIN_TEMPLATE_IDS = {template.template_id for template in _BUILTIN_TEMPLATES}
_DEFAULT_CONFIG = PromptInjectionConfig(
    templates=_BUILTIN_TEMPLATES,
    default_enabled_template_ids=(BUILTIN_RUNTIME_CONTEXT_TEMPLATE_ID,),
)
_CONFIG_FILENAME = ".prompt_injections.json"


def _builtin_templates_with_placements(raw_map: object) -> tuple[PromptTemplate, ...]:
    placement_map = raw_map if isinstance(raw_map, dict) else {}
    return tuple(
        PromptTemplate(
            template_id=template.template_id,
            name=template.name,
            content=template.content,
            built_in=True,
            placement=normalize_placement(placement_map.get(template.template_id, template.placement)),
        )
        for template in _BUILTIN_TEMPLATES
    )


def normalize_placement(placement: str) -> str:
    normalized = str(placement or "").strip().lower()
    if normalized not in VALID_POSITIONS:
        return POSITION_APPEND
    return normalized


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


def create_user_template(
    name: str,
    content: str,
    template_id: str | None = None,
    placement: str = POSITION_APPEND,
) -> PromptTemplate:
    normalized_id = (template_id or "").strip() or str(uuid4())
    if normalized_id in _BUILTIN_TEMPLATE_IDS:
        raise ValueError("User template id conflicts with a built-in template id.")
    return PromptTemplate(
        template_id=normalized_id,
        name=_normalize_name(name),
        content=_normalize_content(content),
        built_in=False,
        placement=normalize_placement(placement),
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
) -> tuple[list[str], list[str]]:
    enabled = set(unique_existing_template_ids(config, enabled_template_ids))
    prepend_sections: list[str] = []
    append_sections: list[str] = []
    for template in config.templates:
        if template.template_id not in enabled:
            continue
        content = template.content.strip()
        if not content:
            continue
        if normalize_placement(template.placement) == POSITION_PREPEND:
            prepend_sections.append(content)
        else:
            append_sections.append(content)
    return prepend_sections, append_sections


def resolve_template_contents_for_ids(
    config: PromptInjectionConfig, template_ids: Sequence[str]
) -> list[str]:
    enabled = set(unique_existing_template_ids(config, template_ids))
    resolved: list[str] = []
    for template in config.templates:
        if template.template_id not in enabled:
            continue
        content = template.content.strip()
        if content:
            resolved.append(content)
    return resolved


def effective_node_template_ids(
    config: PromptInjectionConfig,
    global_enabled_template_ids: Sequence[str],
    local_enabled_template_ids: Sequence[str],
    locally_disabled_global_template_ids: Sequence[str],
) -> tuple[str, ...]:
    global_enabled = set(unique_existing_template_ids(config, global_enabled_template_ids))
    local_enabled = set(unique_existing_template_ids(config, local_enabled_template_ids))
    locally_disabled = set(
        unique_existing_template_ids(config, locally_disabled_global_template_ids)
    )
    ordered: list[str] = []
    for template in config.templates:
        template_id = template.template_id
        if template_id in local_enabled or (
            template_id in global_enabled and template_id not in locally_disabled
        ):
            ordered.append(template_id)
    return tuple(ordered)


def derive_node_template_overrides(
    config: PromptInjectionConfig,
    global_enabled_template_ids: Sequence[str],
    effective_template_ids: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    global_enabled = set(unique_existing_template_ids(config, global_enabled_template_ids))
    effective = set(unique_existing_template_ids(config, effective_template_ids))
    local_enabled: list[str] = []
    locally_disabled: list[str] = []
    for template in config.templates:
        template_id = template.template_id
        if template_id in effective and template_id not in global_enabled:
            local_enabled.append(template_id)
        elif template_id in global_enabled and template_id not in effective:
            locally_disabled.append(template_id)
    return tuple(local_enabled), tuple(locally_disabled)


def compose_prompt(
    base_prompt: str,
    prepend_template_contents: Sequence[str],
    append_template_contents: Sequence[str],
    one_off_text: str = "",
    one_off_placement: str = POSITION_APPEND,
) -> str:
    normalized_base = base_prompt or ""
    prepend = [text.strip() for text in prepend_template_contents if str(text).strip()]
    append = [text.strip() for text in append_template_contents if str(text).strip()]
    normalized_one_off = normalize_one_off_text(one_off_text)
    normalized_one_off_placement = normalize_placement(one_off_placement)
    if normalized_one_off:
        if normalized_one_off_placement == POSITION_PREPEND:
            prepend.append(normalized_one_off)
        else:
            append.append(normalized_one_off)

    if not prepend and not append:
        return normalized_base
    parts: list[str] = []
    if prepend:
        parts.extend(prepend)
    if normalized_base.strip():
        parts.append(normalized_base.rstrip())
    if append:
        parts.extend(append)
    return "\n\n".join(parts)


def normalize_run_options(
    config: PromptInjectionConfig, run_options: PromptInjectionRunOptions | None
) -> PromptInjectionRunOptions:
    if run_options is None:
        return PromptInjectionRunOptions(
            enabled_template_ids=unique_existing_template_ids(
                config, config.default_enabled_template_ids
            ),
            one_off_text="",
            one_off_placement=POSITION_APPEND,
        )
    return PromptInjectionRunOptions(
        enabled_template_ids=unique_existing_template_ids(
            config, run_options.enabled_template_ids
        ),
        one_off_text=normalize_one_off_text(run_options.one_off_text),
        one_off_placement=normalize_placement(run_options.one_off_placement),
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

        builtin_templates = _builtin_templates_with_placements(
            payload.get("builtin_template_placements", {})
        )
        user_templates = self._load_user_templates(payload.get("templates", []))
        all_templates = builtin_templates + tuple(user_templates)

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
        builtin_template_placements = {
            template.template_id: normalize_placement(template.placement)
            for template in normalized.templates
            if template.built_in
        }
        payload = {
            "version": 2,
            "templates": [
                {
                    "id": template.template_id,
                    "name": template.name,
                    "content": template.content,
                    "placement": normalize_placement(template.placement),
                }
                for template in normalized.templates
                if not template.built_in
            ],
            "builtin_template_placements": builtin_template_placements,
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
                    placement=normalize_placement(item.get("placement", POSITION_APPEND)),
                )
            )
        return loaded

    def _normalize_config(self, config: PromptInjectionConfig) -> PromptInjectionConfig:
        ordered_templates: list[PromptTemplate] = []
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for base in _BUILTIN_TEMPLATES:
            seen_ids.add(base.template_id)
            seen_names.add(base.name.casefold())
        for template in config.templates:
            if template.template_id in _BUILTIN_TEMPLATE_IDS:
                placement = normalize_placement(template.placement)
                for built_in_template in _BUILTIN_TEMPLATES:
                    if built_in_template.template_id == template.template_id:
                        ordered_templates.append(
                            PromptTemplate(
                                template_id=built_in_template.template_id,
                                name=built_in_template.name,
                                content=built_in_template.content,
                                built_in=True,
                                placement=placement,
                            )
                        )
                        break
                continue
            try:
                normalized_name = _normalize_name(template.name)
                normalized_content = _normalize_content(template.content)
            except ValueError:
                continue
            template_id = (template.template_id or "").strip()
            if not template_id or template_id in seen_ids:
                template_id = str(uuid4())
                while template_id in seen_ids:
                    template_id = str(uuid4())
            name_key = normalized_name.casefold()
            if name_key in seen_names:
                continue
            seen_ids.add(template_id)
            seen_names.add(name_key)
            ordered_templates.append(
                PromptTemplate(
                    template_id=template_id,
                    name=normalized_name,
                    content=normalized_content,
                    built_in=False,
                    placement=normalize_placement(template.placement),
                )
            )
        # Ensure all built-ins exist even if missing from incoming config.
        builtin_ids_in_output = {t.template_id for t in ordered_templates if t.built_in}
        for built_in_template in _BUILTIN_TEMPLATES:
            if built_in_template.template_id not in builtin_ids_in_output:
                ordered_templates.insert(
                    0,
                    PromptTemplate(
                        template_id=built_in_template.template_id,
                        name=built_in_template.name,
                        content=built_in_template.content,
                        built_in=True,
                        placement=built_in_template.placement,
                    ),
                )
        templates = tuple(ordered_templates)
        normalized_ids = unique_existing_template_ids(
            PromptInjectionConfig(templates, ()),
            config.default_enabled_template_ids,
        )
        return PromptInjectionConfig(templates=templates, default_enabled_template_ids=normalized_ids)
