# llm Developer Guide

## Purpose
Defines provider contracts and the registry used by the UI and worker layer to invoke CLI-based LLMs.

## Contents
- `base_provider.py`: `BaseLLMProvider` interface and `LLMProviderRegistry`.
- `claude_provider.py`: Claude model list, command builder, and Claude-specific structured-output parsing.
- `codex_provider.py`: Codex model list, reasoning-effort suffix parsing, command builder, and Codex-specific structured-output parsing.
- `gemini_provider.py`: Gemini model list and command builder.
- `profiles.py`: Discovers per-provider account profiles by scanning the user's home directory and maps a profile to the environment overlay that selects it.
- `prompt_injection.py`: Prompt template models, persistent JSON storage, run-option normalization, per-node effective-selection helpers, and prompt assembly helpers that place enabled template content plus optional one-off context on either side of the base prompt.
- `__init__.py`: Explicitly re-exports all provider modules so they self-register at startup.

## Current Model Sets
- Claude: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex CLI / OpenAI: GPT-5.5, GPT-5.4, and GPT-5.3 Codex, each with `low`, default (medium), `high`, and `xhigh` reasoning-effort options.
- Gemini: Gemini 3.1 Pro (Preview), Gemini 3 Flash (Preview), Gemini 2.5 Pro, Gemini 2.5 Flash, and Gemini 2.5 Flash Lite.

## Provider Contract
- `name` and `display_name` identify the provider in UI and registry.
- `get_models()` returns `(model_id, label)` tuples for selection widgets.
- `build_command(prompt, model, working_directory, session_id)` returns argv for subprocess execution.
- `uses_stdin` and `get_stdin_prompt()` define how prompt text is delivered to the subprocess. Claude and Gemini use stdin; Codex passes the prompt as a command argument.
- `supports_session_resume(model)` declares whether a model can reuse a prior CLI session.
- `supports_profiles()` declares whether the provider exposes selectable account profiles (config-home directories). Claude and Codex return `True`; Gemini returns `False`.
- `uses_structured_output(model)` declares whether the worker should parse structured CLI output instead of streaming plain text directly.
- `parse_structured_output(lines)` must be provider-specific whenever JSON schemas differ. The base implementation only joins raw structured lines and extracts the resumable conversation identifier (`session_id` or `thread_id`); it is not responsible for guessing the final assistant message.

## Session Resume Rules
- Claude and Codex are the only resumable providers.
- Gemini must report no session-resume support so the GUI can disable and clear the checkbox.
- Saved session IDs are persisted by the GUI on each LLM node, not in a separate sidecar file.
- Claude resumes with `--resume <session_id>`.
- Codex JSON output emits `thread.started` with `thread_id`; the GUI stores that thread id in the node's saved-session slot and resumes with `codex exec ... resume <thread_id> <prompt>`.
- Codex uses `-C <dir>` for working-directory scoping.

## Structured Output Parsing
- Claude parsing should prefer the provider's explicit result or message fields and only fall back to flattened content blocks when those are absent. If multiple explicit result/message payloads arrive, the parser returns the last non-empty candidate.
- Codex parsing should handle both legacy top-level terminal message fields and current `item.completed` events whose nested `item` carries `type=agent_message` plus the final text payload.
- If a provider's event schema changes, update only that provider's parser. Do not push schema guesses back into `BaseLLMProvider`.

## Prompt Injection
- Prompt template state is persisted in repo-root `.prompt_injections.json` and loaded through `PromptInjectionStore`.
- Built-in template `runtime_context_headless` is always available and is enabled by default on first load.
- Each template has a persistent `placement` value (`prepend` or `append`), configured from the prompt-template dialog.
- `PromptInjectionRunOptions` carries `one_off_placement` so one-off run context can also be prepended or appended.
- `effective_node_template_ids()` and `derive_node_template_overrides()` merge workflow-global enabled-template IDs with a node's saved local additions and per-side opt-outs.
- `compose_prompt()` performs deterministic assembly in three regions: prepend injections, base prompt, append injections, joined as plain text blocks without bracketed section headers.

## Account Profiles
- A "profile" is a CLI config-home directory selected through an environment variable: Codex honours `CODEX_HOME`, Claude honours `CLAUDE_CONFIG_DIR`.
- `discover_profiles(provider_name)` scans `~` for the provider's config dirs. `~/.codex` and `~/.claude` are the default profile (no env override); suffixed dirs like `~/.codex-shlomo` or `~/.claude-michael` become profiles named by their suffix (`shlomo`, `michael`).
- `resolve_profile_env(provider_name, profile_name)` returns the env overlay to merge into the subprocess. The default profile, an empty selection, and unknown names all resolve to `{}` (CLI default) so stale workflows still run.
- The GUI stores the chosen profile on each `LLMNode` as `profile_name`; `execution.py` resolves it to an env overlay passed to `LLMWorker`.

## When To Edit
- Add or remove models for a provider: corresponding `*_provider.py`.
- Add a new provider: create the provider file and import it in `__init__.py`.
- Add profile support to a provider: override `supports_profiles()` and add a rule to `_PROVIDER_RULES` in `profiles.py`.
- Change global provider API rules: `base_provider.py`.
- Change template storage rules, limits, or prompt assembly format: `prompt_injection.py`.
