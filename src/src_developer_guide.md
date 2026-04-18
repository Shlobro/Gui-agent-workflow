# src Developer Guide

## Purpose
`src/` is the runtime package for GUI Workflow. It contains all app code grouped by UI, provider integration, and background execution.

## Folder Map
- `gui/`: Qt graphics-based workflow editor and main-window shell.
- `llm/`: Provider abstraction and concrete CLI adapters (Claude, Codex, Gemini).
- `workers/`: Threaded subprocess workers used to execute LLM, git, and script commands without blocking UI.

## Data Flow
1. UI collects node configuration through `PropertiesPanel`. The panel stays visible at all times: with one selected node it shows node-edit forms, with one selected connection it shows arrow details plus connection-edit shortcuts, otherwise it shows a workflow overview summary. Content fields commit directly to node attributes, while title, model, resume-session toggle, op-type, condition-type, loop-count, join-count, and git-action changes go through canvas undo handlers.
2. `WorkflowCanvas` in `src/gui/canvas/` handles graph interaction, connection routing, clipboard, undo/redo, and save/load. It supports LLM, file-op, conditional, attention, loop, join, git-action, and script-runner nodes. Manual connection vertices are serialized in each connection record as `vertices` and restored through load, undo, and paste flows.
3. Canvas offers three run modes: Run All, Run Selected, and Run From Here. Pre-run validation requires prompt plus resolvable model for `LLMNode`; filename for `FileOpNode`; known `condition_type` and a filename only for filename-scoped conditions on `ConditionalNode`; non-empty message for `AttentionNode`; valid git enums plus commit-message requirements for `GitActionNode`; and a selected `.bat`, `.cmd`, or `.ps1` path for `ScriptNode`.
4. `LLMNode` execution uses `LLMWorker` in a background `QThread`. Prompt text is assembled through `src.llm.prompt_injection.compose_prompt(...)` using the active global template selection plus each node's saved prepend/append override state. Claude and Codex providers use structured CLI output so the worker can capture resumable conversation IDs (`session_id` for Claude, `thread_id` for Codex); Gemini remains plain-text.
5. LLM session state is split between per-node fields on `LLMNode` (`resume_session_enabled`, `save_session_enabled`, `save_session_name`, `resume_named_session_name`, `saved_session_id`, `saved_session_provider`) and a workflow-level named-session store on `WorkflowCanvas`. If a loaded workflow contains saved node or named sessions, `MainWindow` asks on the next run whether to resume them or clear them and start fresh.
6. When `resume_session_enabled` is checked on a Claude or Codex node, later calls reuse that node's saved session ID. Named-session resume pulls from the workflow-level store instead, but only when the target session already has a captured ID, matches the current provider, and the graph contains a directed path from the save-owner node to the current load node.
7. Canvas execution serializes concurrent invocations that reuse the same resumable conversation, whether the reuse key is the node-local previous session or a workflow-level named session.
8. Copy/paste always produces a fresh LLM node session state. Pasted nodes keep `resume_session_enabled`, but named-session save/resume bindings and captured provider session IDs are cleared.

## Current Built-In Models
- Claude provider: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex CLI / OpenAI provider: GPT-5.4 and GPT-5.3 Codex, each with `low`, default (medium), `high`, and `xhigh` effort options.
- Gemini provider: Gemini 3.1 Pro (Preview), Gemini 3 Flash (Preview), Gemini 2.5 Pro, Gemini 2.5 Flash, and Gemini 2.5 Flash Lite.

## When To Edit What
- Graph interaction and serialization behavior: `gui/`.
- UI shell behavior, save/load prompts, and panel flows: `gui/main_window.py` plus `gui/properties_panel.py`.
- Add or adjust model catalogs and CLI flags: `llm/`.
- Change prompt template storage, prompt assembly order, or built-in runtime context text: `llm/prompt_injection.py`.
- Process execution, cancellation, timeout handling, or structured result capture: `workers/`.
