# src Developer Guide

## Purpose
`src/` is the runtime package for GUI Workflow. It contains all app code grouped by UI, provider integration, and background execution.

## Folder Map
- `gui/`: Qt graphics-based workflow editor and main window shell.
- `llm/`: Provider abstraction and concrete CLI adapters (Claude, Codex, Gemini).
- `workers/`: Threaded subprocess workers used to execute LLM and git commands without blocking UI.
- `__init__.py`: Package marker.

## Data Flow
1. UI collects node configuration through `PropertiesPanel`. Content fields commit directly to node attributes on focus loss or explicit commit, while title, model, op-type, condition-type, loop-count, and git-action changes go through canvas undo handlers. `PropertiesPanel.commit_pending_edits()` is invoked before run/save and before panel node switches so canvas state stays in sync. `MainWindow` persists panel width and panel-local text zoom in `QSettings`.
2. `WorkflowCanvas` in `src/gui/canvas/` handles graph interaction, connection routing, clipboard, undo/redo, and save/load. It supports LLM, file-op, conditional, attention, loop, and git-action nodes. `load_workflow_data()` parses and validates the payload before mutating the scene; malformed node records abort the load, while malformed connections are silently dropped.
3. Canvas offers three run modes: Run All, Run Selected, and Run From Here. Pre-run validation requires: prompt plus resolvable model for `LLMNode`; filename for `FileOpNode`; known `condition_type` and a filename only for filename-scoped conditions on `ConditionalNode`; non-empty message for `AttentionNode`; valid git enums plus commit-message requirements for `GitActionNode`. `LoopNode` needs no extra validation because `loop_count` is validated at parse/load time.
4. `LLMNode` execution uses `LLMWorker` in a background `QThread`. `GitActionNode` execution uses `GitWorker` in a background `QThread` with streaming output, cancellation, and watchdog timeout handling. `FileOpNode`, `AttentionNode`, and `LoopNode` execute synchronously on the GUI thread. Loop execution uses status `looping` while in progress, routes the `loop` branch exactly `loop_count` times for each loop thread, and routes the `done` branch on the next loop-node re-entry, so loop bodies need an explicit feedback edge back into the loop input. `ConditionalNode` execution is mixed: file-based evaluators stay synchronous, while `git_changes` runs `git status --porcelain --untracked-files=all` against the selected project folder in a background `GitWorker` with live streamed git output, a 15-second timeout, and a clear timeout error if git does not return in time. Child triggering is deferred with `QTimer.singleShot(0, ...)`. Trigger calls carry both `lineage_token` and `loop_token`.
5. Active-border animation is timer-driven for all non-start workflow nodes while status is `running` or `looping`, and selected active nodes use a stronger pulsing selection ring keyed to the same active color so running state remains obvious.
6. File-op paths are resolved against the selected project folder and blocked if they are absolute or escape the folder via traversal. `create_file` reports `Already exists` when the target file already exists and errors when the target exists as a directory or non-file path.
7. Streamed output lines and terminal node results are appended live to node state and surfaced in the properties panel output area for whichever node is currently selected. For LLM nodes, prompt and output share a vertical splitter so users can rebalance them while reviewing results.
8. UI scrollbar theming is centered in `gui/main_window.py`, with widget-local overrides in `gui/properties_panel.py`, `gui/llm_widget.py`, and `gui/project_chooser.py` where local stylesheets would otherwise bypass the global theme. The current theme uses 18 px capsule rails with inset bordered capsule handles. Workflow save/load and project-folder pickers use non-native `QFileDialog` options so this styling is visible in those pickers.

## Current Built-In Models
- Claude provider: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex CLI / OpenAI provider: GPT-5.4 and GPT-5.3 Codex, each with `low`, default (medium), `high`, and `xhigh` effort options.
- Gemini provider: models declared in `llm/gemini_provider.py`.

## When To Edit What
- Graph interaction and serialization behavior: `gui/`.
- UI shell styling and shared scrollbar visuals: `gui/main_window.py` plus local GUI widget stylesheets.
- Add or adjust model catalogs and CLI flags: `llm/`.
- Process execution, cancellation, and timeout handling: `workers/`.

## Attention And Git-Change Conditions
- `WorkflowCanvas` includes an `AttentionNode` path alongside the other built-in node types. Attention nodes execute synchronously on the UI thread and require a non-empty message at run time rather than load time.
- `ConditionalNode` registry entries describe whether a condition requires a filename. `git_changes` evaluates the selected project folder in a background `GitWorker` with `git status --porcelain --untracked-files=all`, streams git output into the node log, and fails after 15 seconds if git hangs; `file_empty` still evaluates a confined file path on the UI thread.
