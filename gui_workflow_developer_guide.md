# GUI Workflow Developer Guide (Repo Root)

## Purpose
GUI Workflow is a PySide6 desktop application for building and executing node-based LLM workflows. Users create nodes, connect them from a permanent Start node, and run the resulting trigger-driven graph.

## Top-Level Map
- `workflow_entry.py`: Canonical app launcher. Creates `QApplication`, configures DPI policy, loads providers, and opens the main window.
- `run_gui_workflow.bat`: Windows launcher script that runs `workflow_entry.py`.
- `src/`: Application package (GUI, provider registry, worker threads).
- `requirements.txt`: Python runtime dependencies.
- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`: Governance prompt files for coding agents.
- `.claude/settings.local.json`: Local Claude permission override for this workspace.
- `.gitignore`: Ignore rules including Python caches and temp paths.

## Runtime Flow
1. Start the app through `run_gui_workflow.bat` or directly with `python workflow_entry.py`.
2. Importing `src.llm` registers provider implementations into `LLMProviderRegistry`.
3. `ProjectChooserDialog` opens first so the user can pick or re-pick a project folder. Recent choices are persisted in `.recent_folders.json` at the repo root. Cancelling the dialog still opens the main window; a folder can be chosen later via File -> Open Project Folder.
4. `src.gui.main_window.MainWindow` creates the menu bar, toolbar, status shell, and mounts a horizontal splitter containing `WorkflowCanvas` and `PropertiesPanel`. The chosen project folder is set as the LLM/git subprocess `cwd` via `WorkflowCanvas.set_working_directory()`. Panel width and panel text zoom are restored and persisted through `QSettings`. `MainWindow` also applies the default rounded scrollbar theme used across the shell UI.
5. Canvas interactions create nodes and connections, support wheel zoom and right-drag panning, allow left-drag rubber-band multi-selection, render selected nodes with a light-blue neon frame, keep background grid dots visible with fixed on-screen size across zoom levels, auto-expand scene bounds so corner nodes remain reachable, route connection lines around node bounds, keep arrowheads visible by ending slightly before the input port center, show direction cues on ports, expose an expanded connection hit area, suspend wheel zoom while model dropdowns are open, support copy/paste with cumulative offsets, and wrap graph mutations in undo/redo commands. Nodes are compact painted items (64 px tall for LLM, file-op, git-action, and attention nodes; 80 px tall for conditional and loop nodes) that edit through the resizable `PropertiesPanel`. Ctrl+mouse-wheel inside the panel changes panel text size, and LLM prompt/output editors share space evenly once output is visible. `ConditionalNode` has true/false output ports, `LoopNode` has loop/done ports, and connections from these ports carry a `source_port` field so execution routes only the matching branch.
6. Three run modes are available. **Run All** starts from the permanent Start node, validates all reachable nodes, and then fires Start's direct children. Validation rules: `LLMNode` requires prompt plus a model that resolves to a registered provider; `FileOpNode` requires a filename; `ConditionalNode` requires a known `condition_type` and a filename only when that condition type declares one; `AttentionNode` requires a non-empty message at run time; `LoopNode` has no extra validation requirement; `GitActionNode` requires `git_action` in `{git_add, git_commit, git_push}` and `msg_source` in `{static, from_file}`, and `git_commit` also requires a non-empty commit message or commit-message file depending on `msg_source`. LLM nodes execute in `LLMWorker`; git-action nodes execute in `GitWorker` with live streamed output and timeout enforcement. File-op, attention, and loop nodes execute synchronously on the UI thread with downstream fan-out queued through the Qt event loop. `git_changes` runs `git status --porcelain --untracked-files=all` against the selected project folder in a background `GitWorker`, streams git output into the node log, and fails with a clear timeout error after 15 seconds if git does not return. Other conditional evaluators still execute synchronously. Deferred callbacks re-check that the source-to-target edge still exists before firing. Run completion waits for both active invocations and queued child triggers to drain. File-op paths must stay inside the selected project folder. `create_file` reports `Already exists` for existing files and errors if the target already exists as a directory or non-file path. **Run Selected** fires only the selected node(s) with no fan-out. **Run From Here** fires the selected node and propagates to its descendants. `MainWindow` calls `PropertiesPanel.commit_pending_edits()` before run/save operations. `PropertiesPanel` itself calls `commit_pending_edits()` before switching to a different node (inside `show_for_node()` and `hide_panel()`). Workflow payload parsing is atomic: parse/validate first, then clear/apply only on success.

## Built-In Models
- Claude: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex CLI / OpenAI: GPT-5.4 and GPT-5.3 Codex, each with `low`, default (medium), `high`, and `xhigh` reasoning effort.
- Gemini: model catalog defined in `src/llm/gemini_provider.py`.

## User Data and Artifacts
- Workflow graphs are user-saved JSON files chosen from the Save/Load dialogs. Workflow files can be saved anywhere.
- `saves/*.json` holds tracked workflow fixtures used for manual and testing scenarios.
- Node output is held in memory during runtime and displayed in the `PropertiesPanel` for the currently selected node.
- All LLM and git subprocess calls run with the selected project folder as their working directory.
- Recently opened project folders are stored in `.recent_folders.json` at the repo root (gitignored).

## Change Map
- App startup and entrypoint behavior: `workflow_entry.py`, `run_gui_workflow.bat`.
- Canvas interaction, node/connection creation, keyboard/mouse events: `src/gui/canvas/__init__.py`.
- Workflow run/stop execution engine: `src/gui/canvas/execution.py`.
- Graph mutation helpers, clipboard, save/load: `src/gui/canvas/io.py`.
- Workflow save/load serialization, payload validation, and provider registry lookup: `src/gui/workflow_io.py`.
- Node rendering and graph item behavior: `src/gui/llm_node.py`.
- File operation and attention nodes: `src/gui/file_op_node.py`.
- Conditional routing node and condition registry: `src/gui/conditional_node.py`.
- Loop routing node: `src/gui/loop_node.py`.
- Git action node: `src/gui/git_action_node.py`.
- Resizable properties panel and form widgets: `src/gui/properties_panel.py`, `src/gui/_panel_forms.py`.
- Model selector dropdown and provider icon rendering: `src/gui/llm_widget.py`, `src/gui/assets/`.
- Save/load and toolbar actions: `src/gui/main_window.py`.
- Provider models and CLI command construction: `src/llm/*_provider.py`.
- Subprocess streaming, cancellation, and timeouts: `src/workers/llm_worker.py`, `src/workers/git_worker.py`.
- Usage and rate-limit detection dialog flow: `src/gui/canvas/execution.py`, `src/gui/dialogs/usage_limit_dialog.py`, `src/gui/main_window.py`.

## Attention And Git-Change Conditions
- `AttentionNode` is a built-in compact workflow node that blocks fan-out on its own branch: it plays `QApplication.beep()`, opens a modal `QMessageBox` (which starts a nested Qt event loop, so other branches and background workers remain active), and then either continues fan-out from this node or calls `stop_all()` based on the user's choice. It is a single-branch gate, not a global workflow pause.
- `ConditionalNode` supports both `file_empty` and `git_changes`. `file_empty` evaluates a confined project-relative file path on the UI thread. `git_changes` evaluates the selected project folder in a background `GitWorker` by running `git status --porcelain --untracked-files=all`, streams git output into the node log, uses a 15-second timeout, and routes true when any staged, unstaged, or untracked changes exist.
