# llm Developer Guide

## Purpose
Defines provider contracts and the registry used by the UI and worker layer to invoke CLI-based LLMs.

## Contents
- `base_provider.py`: `BaseLLMProvider` interface and `LLMProviderRegistry`.
- `claude_provider.py`: Claude model list and command builder.
- `codex_provider.py`: Codex model list, reasoning-effort suffix parsing, command builder, and optional working-directory scoping/output path.
- `gemini_provider.py`: Gemini model list and command builder.
- `prompt_injection.py`: Prompt template models, persistent JSON storage, run-option normalization, and prompt assembly helpers that place enabled template content plus optional one-off context on either side of the base prompt (`prepend` or `append`).
- `__init__.py`: Explicitly re-exports all provider modules so they self-register at startup and pass static unused-import checks.

## Current Model Sets
- Claude: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex CLI / OpenAI: GPT-5.4 and GPT-5.3 Codex, each with `low`, default (medium), `high`, and `xhigh` reasoning-effort options.
- Gemini: Gemini 3.1 Pro (Preview), Gemini 3 Flash (Preview), Gemini 2.5 Pro, Gemini 2.5 Flash, and Gemini 2.5 Flash Lite.

## Provider Contract
- `name` and `display_name` identify the provider in UI/registry.
- `get_models()` returns `(model_id, label)` tuples for selection widgets.
- `build_command()` returns argv for subprocess execution.
- `uses_stdin`/`get_stdin_prompt()` controls prompt transport behavior.

## Prompt Injection
- Prompt template state is persisted in repo-root `.prompt_injections.json` and loaded through `PromptInjectionStore`.
- Built-in template `runtime_context_headless` is always available and is enabled by default on first load.
- Each template has a persistent `placement` value (`prepend` or `append`), configured from the prompt-template dialog.
- Built-in template placement is persisted in the same config file (`builtin_template_placements`) so user-selected built-in placement survives restart.
- `PromptInjectionRunOptions` carries `one_off_placement` so one-off run context can also be prepended or appended.
- `compose_prompt()` performs deterministic assembly in three regions: prepend-injections, base prompt, append-injections, joined as plain text blocks without bracketed section headers.

## When To Edit
- Add/remove models for a provider: corresponding `*_provider.py`.
- Add a new provider: create provider file and import it in `__init__.py`.
- Change global provider API rules: `base_provider.py`.
- Change template storage rules, limits, or prompt assembly format: `prompt_injection.py`.
