# src Developer Guide

## Purpose
`src/` is the runtime package for GUI Workflow. It contains all app code grouped by UI, provider integration, and background execution.

## Folder Map
- `gui/`: Qt graphics-based workflow editor and main window shell.
- `llm/`: Provider abstraction and concrete CLI adapters (Claude, Codex, Gemini).
- `workers/`: Threaded subprocess worker used to execute provider calls without blocking UI.
- `__init__.py`: Package marker.

## Data Flow
1. UI collects node prompts and model selections.
2. Canvas resolves upstream placeholders and chooses a provider via `LLMProviderRegistry`.
3. `LLMWorker` runs the provider command in a background `QThread`.
4. Streamed output lines are appended live into the active node.

## When To Edit What
- Graph interaction/serialization behavior: `gui/`.
- Add or adjust model catalogs and CLI flags: `llm/`.
- Process execution, cancellation, and timeout handling: `workers/`.
