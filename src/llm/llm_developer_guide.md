# llm Developer Guide

## Purpose
Defines provider contracts and the registry used by the UI and worker layer to invoke CLI-based LLMs.

## Contents
- `base_provider.py`: `BaseLLMProvider` interface, `ModelEntry`/`ModelVariant` catalog types, effort-variant helpers, legacy-id normalization, and `LLMProviderRegistry`.
- `claude_provider.py`: Claude catalog, command builder, and Claude-specific structured-output parsing.
- `codex_provider.py`: Codex catalog, reasoning-effort suffix parsing, command builder, and Codex-specific structured-output parsing.
- `grok_provider.py`: Grok Build CLI catalog, command builder, and JSON result parsing.
- `opencode_provider.py`: OpenCode CLI catalog (free OpenCode Zen models), command builder, and JSON-event output parsing.
- `profiles.py`: Discovers per-provider account profiles by scanning the user's home directory and maps a profile to the environment overlay that selects it.
- `prompt_injection.py`: Prompt template models, persistent JSON storage, run-option normalization, per-node effective-selection helpers, and prompt assembly helpers that place enabled template content plus optional one-off context on either side of the base prompt.
- `__init__.py`: Explicitly re-exports all provider modules so they self-register at startup. Registry order (and dropdown order): claude, codex, grok, opencode.

## Current Model Sets
- Claude: Opus 5 (`claude-opus-5`, efforts low/medium/high/xhigh/max, default high) and Sonnet 5 (`claude-sonnet-5`, efforts low/medium/high/xhigh, default medium). Efforts map onto the CLI `--effort` flag.
- Codex CLI / OpenAI: GPT-5.6 family — Sol (`gpt-5.6-sol`, default low, efforts through ultra), Terra (`gpt-5.6-terra`, default medium, efforts through ultra), and Luna (`gpt-5.6-luna`, default medium, efforts through max). Efforts map onto `-c model_reasoning_effort=<v>`.
- Grok Build / xAI: Grok 4.6 with low/medium/high/xhigh efforts and Grok 4.5 with low/medium/high efforts, mapped onto `--effort`. Run `grok models` to check availability.
- OpenCode: free OpenCode Zen models only (`opencode/...` provider namespace): `x-preview-f-free` (Ox Alpha Free), `mimo-v2.5-free`, `hy3-free`, `nemotron-3-ultra-free`, `nemotron-3.5-lightning-free`, and `muse-spark-1.2-contributor-free` (no variants). Catalog ids are stored bare; `build_command` prefixes them with `opencode/`.

## Model Catalog And Variants
- Providers implement `get_model_entries()` returning `ModelEntry(model_id, label, variants, default_variant_id)`.
- `variants` hold selectable options such as reasoning-effort levels; entries without variants expose a single fixed model.
- The UI shows one row per entry in the Model dropdown; variants appear only after a model is picked (second "Effort" control owned by `_LLMForm`).
- Stored node ids compose as `<model_id>:<variant_id>` whenever variants exist (`split_model_variant`/`compose_model_variant`). `get_models()` flattens entries back into full `(id, label)` tuples so registry lookups keep matching stored ids.
- `find_model_entry(full_or_bare_id)` resolves an id onto its `(entry, variant)` pair for any provider.

## Provider Contract
- `name` and `display_name` identify the provider in UI and registry.
- `get_model_entries()` returns the structured catalog; `get_models()` derives flat lookup tuples from it.
- `build_command(prompt, model, working_directory, session_id)` returns argv for subprocess execution. The incoming `model` is the stored composed id; providers split off the variant suffix themselves.
- `uses_stdin` and `get_stdin_prompt()` define how prompt text is delivered to the subprocess. Claude uses stdin; Codex, Grok, and OpenCode pass the prompt as the final command argument.
- `supports_session_resume(model)` declares whether a model can reuse a prior CLI session.
- `supports_profiles()` declares whether the provider exposes selectable account profiles (config-home directories). Claude and Codex return `True`; Grok and OpenCode return `False`.
- `uses_structured_output(model)` declares whether the worker should parse structured CLI output instead of streaming plain text directly.
- `structured_output_progress_lines(line, model)` optionally maps one structured event line into zero or more human-readable progress lines for the node output while the subprocess is still running.
- `parse_structured_output(lines)` must be provider-specific whenever JSON schemas differ. The base implementation only joins raw structured lines and extracts the resumable conversation identifier (`session_id` or `thread_id`); it is not responsible for guessing the final assistant message.

## Session Resume Rules
- Claude, Codex, Grok, and OpenCode are the resumable providers.
- Saved session IDs are persisted by the GUI on each LLM node, not in a separate sidecar file.
- Claude resumes with `--resume <session_id>`.
- Codex JSON output emits `thread.started` with `thread_id`; the GUI stores that thread id in the node's saved-session slot and resumes with `codex exec ... resume <thread_id> <prompt>`.
- Codex uses `-C <dir>` for working-directory scoping.
- Grok resumes with `--resume <session_id>`; session ids come from the JSON result object's `sessionId`. It always runs with `--always-approve --no-alt-screen --no-auto-update --output-format json` and scopes with `--cwd <dir>`.
- OpenCode resumes with `--session <session_id>`; session ids (`ses_...`) come from each JSON event's top-level `sessionID`. It uses `--dir <dir>` for working-directory scoping and always runs with `--format json --auto`.

## Structured Output Parsing
- Claude parsing should prefer the provider's explicit result or message fields and only fall back to flattened content blocks when those are absent. If multiple explicit result/message payloads arrive, the parser returns the last non-empty candidate.
- Codex parsing should handle both legacy top-level terminal message fields and current `item.completed` events whose nested `item` carries `type=agent_message` plus the final text payload.
- Grok output is one pretty-printed JSON object (`text`, `stopReason`, `sessionId`, usage fields); the parser scans the whole blob with `raw_decode` so interleaved non-JSON noise cannot break it and takes the last object carrying a `text` string.
- OpenCode parsing joins every `text` event's `part.text` in arrival order into the final response and takes the session id from top-level `sessionID`. Live progress maps only `tool_use` events (started/finished/failed) plus non-JSON CLI notices; `step_start`, `text`, and `step_finish` events stay silent. ANSI color codes are stripped from non-JSON lines.
- Codex live progress should stay concise and human-readable. Surface useful thread/tool/status milestones in the node output, but do not dump raw JSON lines into the GUI.
- If a provider's event schema changes, update only that provider's parser. Do not push schema guesses back into `BaseLLMProvider`.

## Model ID Normalization
- `normalize_model_id()` in `base_provider.py` maps saved legacy model IDs onto the currently registered catalog before provider lookup or UI selection. Aliases preserve the effort token where the target supports it.
- Older Opus ids map onto `claude-opus-5:<same-effort>` (bare old Opus ids become `claude-opus-5:high`).
- Older Sonnet ids map onto `claude-sonnet-5:<same-effort>` except the retired `max` effort, which maps to `claude-sonnet-5:xhigh`; bare old Sonnet and Haiku ids become `claude-sonnet-5:medium`.
- Retired Codex ids map onto the GPT-5.6 family: `gpt-5.4*` and `gpt-5.5*` onto Terra (preserving effort; bare becomes medium) and `gpt-5.3-codex*` onto Sol (bare becomes low).

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
- Add or remove models or variants for a provider: corresponding `*_provider.py` (`ENTRIES` list).
- Add a new provider: create the provider file and import it in `__init__.py`.
- Add profile support to a provider: override `supports_profiles()` and add a rule to `_PROVIDER_RULES` in `profiles.py`.
- Change global provider API rules, variant composition, or normalization: `base_provider.py`.
- Change template storage rules, limits, or prompt assembly format: `prompt_injection.py`.
