# llm Developer Guide

## Purpose
Defines provider contracts and the registry used by the UI and worker layer to invoke CLI-based LLMs.

## Contents
- `base_provider.py`: `BaseLLMProvider` interface and `LLMProviderRegistry`.
- `claude_provider.py`: Claude model list and command builder.
- `codex_provider.py`: Codex model list, reasoning-effort suffix parsing, command builder, and optional working-directory scoping/output path.
- `gemini_provider.py`: Gemini model list and command builder.
- `__init__.py`: Imports all providers so they self-register at startup.

## Current Model Sets
- Claude: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex: GPT-5.3 Codex with `low`, default (medium), `high`, and `xhigh` reasoning-effort options.
- Gemini: See `gemini_provider.py` for the current list exposed to the UI.

## Provider Contract
- `name` and `display_name` identify the provider in UI/registry.
- `get_models()` returns `(model_id, label)` tuples for selection widgets.
- `build_command()` returns argv for subprocess execution.
- `uses_stdin`/`get_stdin_prompt()` controls prompt transport behavior.

## When To Edit
- Add/remove models for a provider: corresponding `*_provider.py`.
- Add a new provider: create provider file and import it in `__init__.py`.
- Change global provider API rules: `base_provider.py`.
