# src Developer Guide

## Purpose
`src/` is the runtime package for GUI Workflow. It contains all app code grouped by UI, provider integration, and background execution.

## Folder Map
- `gui/`: Qt graphics-based workflow editor and main window shell.
- `llm/`: Provider abstraction and concrete CLI adapters (Claude, Codex, Gemini).
- `workers/`: Threaded subprocess worker used to execute provider calls without blocking UI.
- `__init__.py`: Package marker.

## Data Flow
1. UI collects LLMNode prompts/model selections and FileOpNode filenames (with provider logos loaded from `gui/assets/` in a compact model-picker that opens a bounded overlay dropdown anchored to the active window by default, or the canvas viewport when embedded via a graphics proxy). Title edits commit on `editingFinished`; prompt edits are dirtied on text change and committed on focus-out; filename edits are dirtied on text change and committed on focus-out or Enter. `PropertiesPanel.commit_pending_edits()` applies visible edits in a stable order (prompt/filename first, then title) and is invoked before run/save and before panel node switches so canvas state stays in sync. Load/Clear hide the panel before mutating canvas state, and title/model undo-push handlers ignore missing/non-live node IDs.
2. `WorkflowCanvas` handles graph interaction including node/edge editing, wheel-to-zoom, right-drag panning, left-drag rubber-band multi-selection, a zoom-stable dot grid background, auto-expanding scene bounds so moved nodes stay reachable, obstacle-aware connection routing around node boxes (LLMNode, StartNode, FileOpNode; including an immediate reroute after a new connection is created), temporary zoom suspension while model dropdowns are open (wheel then scrolls the dropdown list), and in-memory node clipboard (Ctrl+C copies selected nodes and their internal connections and resets a paste counter; Ctrl+V pastes duplicates with fresh IDs at cumulative offsets of 40 × paste-count px so repeated pastes cascade rather than stack). Every graph mutation (add/delete node, add/delete connection, move, rename, model change, paste) is wrapped in a `QUndoCommand` and pushed onto a `QUndoStack` via the classes in `gui/undo_commands.py`; Ctrl+Z undoes and Ctrl+Y redoes — all Ctrl shortcuts are suppressed while any text widget (`QLineEdit`, `QPlainTextEdit`, `QTextEdit`) has focus so native widget undo still works inside text fields. `load_workflow_data()` parses/normalizes and validates top-level structure (`node_counter`, `start_pos`, `nodes`, `connections`) before any scene mutation, then clears/applies. Malformed node records (non-object, failed deserialization, missing/invalid ID, or duplicate ID) abort the entire load with an error. Malformed connection records are silently dropped because a partial connection set is still a coherent graph. New LLM nodes default to `gemini-3-pro-preview` when that model is registered; otherwise they use the first registered model, and fall back to no model only when no models are available.
3. Canvas offers three run modes: Run All (trigger-driven from Start node, only reachable nodes, upfront validation), Run Selected (fires selected nodes only, no fan-out to children), and Run From Here (fires selected node and all its descendants). Pre-run validation is mixed: LLMNode requires prompt plus a selected model that resolves to a registered provider; FileOpNode requires filename.
4. LLMNode execution uses `LLMWorker` in a background `QThread`. FileOpNode execution runs synchronously in the GUI thread, but child triggering is deferred with `QTimer.singleShot(0, ...)` to avoid synchronous recursive call chains in cyclic file-op graphs. Deferred callbacks re-check that the queued source→target edge still exists before triggering. Run drain checks require both active invocations and queued child triggers to be empty.
5. File-op paths are resolved against the selected project folder and blocked if they are absolute or escape the folder via traversal. `create_file` reports `Already exists` when the target file is already present and errors when the target path exists as a directory/non-file path.
6. Streamed output lines and file-op results are appended live to node state and surfaced in the properties panel output area for whichever node is currently selected.

## Current Built-In Models
- Claude provider: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex provider: GPT-5.3 Codex with `low`, default (medium), `high`, and `xhigh` effort options.
- Gemini provider: models declared in `llm/gemini_provider.py`.

## When To Edit What
- Graph interaction/serialization behavior: `gui/`.
- Add or adjust model catalogs and CLI flags: `llm/`.
- Process execution, cancellation, and timeout handling: `workers/`.
