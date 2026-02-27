# GUI Workflow Developer Guide (Repo Root)

## Purpose
GUI Workflow is a PySide6 desktop application for building and executing node-based LLM workflows. Users create nodes, connect them from a permanent Start node, and run the resulting trigger-driven graph.

## Top-Level Map
- `workflow_entry.py`: Canonical app launcher. Creates `QApplication`, configures DPI policy, loads providers, and opens the main window.
- `run_gui_workflow.bat`: Windows launcher script that runs `workflow_entry.py`.
- `src/`: Application package (GUI, provider registry, worker thread).
- `requirements.txt`: Python runtime dependencies.
- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`: Governance prompt files for coding agents.
- `.claude/settings.local.json`: Local Claude permission override for this workspace.
- `.gitignore`: Ignore rules including Python caches and temp paths.

## Runtime Flow
1. Start the app through `run_gui_workflow.bat` or directly with `python workflow_entry.py`.
2. Importing `src.llm` registers provider implementations into `LLMProviderRegistry`.
3. `ProjectChooserDialog` opens first so the user can pick (or re-pick) a project folder to work in. Recent choices are persisted in `.recent_folders.json` at the repo root. Cancelling the dialog still opens the main window; a folder can be chosen later via File → Open Project Folder.
4. `src.gui.main_window.MainWindow` creates the menu bar, toolbar, status shell, and mounts `WorkflowCanvas`. The chosen project folder is set as the LLM subprocess `cwd` via `WorkflowCanvas.set_working_directory()`.
5. Canvas interactions create nodes/connections, support wheel zoom and right-drag panning, allow left-drag rubber-band multi-selection, render selected nodes with a light-blue neon frame, keep background grid dots visible with fixed on-screen size across zoom levels, auto-expand scene bounds so corner nodes remain reachable, route connection lines around node bounds (including immediate reroute right after connection creation), keep arrowheads visible by ending slightly before the input port center, show direction cues on ports with ingress/egress arrows that protrude from node edges and hide once that side is connected, expose an expanded connection hit area so arrow selection is easier, suspend wheel zoom while model dropdowns are open so wheel input scrolls the model list, copy selected nodes (Ctrl+C) and paste duplicates with fresh IDs at cumulative offsets (40 px × paste count, reset on each copy) preserving internal connections, undo/redo graph mutations (Ctrl+Z / Ctrl+Y) covering add/delete nodes, add/delete connections, node moves, title renames, model changes, and paste operations — all Ctrl shortcuts suppressed while any text widget (QLineEdit, QPlainTextEdit, QTextEdit) has focus so native widget undo still works, and optionally save/load workflow JSON files. Nodes are compact painted items (64 px tall) showing only a colored header strip and title label; all editing is done in the sliding `PropertiesPanel` on the right side of the window.
6. Three run modes are available. **Run All**: starts from the permanent Start node, validates all reachable nodes (LLMNode requires prompt plus a model that resolves to a registered provider; FileOpNode requires filename), then fires Start's direct children. LLM nodes execute in `LLMWorker`; file-op nodes execute synchronously on the UI thread with downstream fan-out queued through the Qt event loop. Deferred callbacks re-check that the source→target edge still exists before firing. Run completion waits for both active invocations and queued child triggers to drain. File-op paths must stay inside the selected project folder (absolute paths and traversal escapes are rejected). `create_file` reports `Already exists` for existing files and raises an error if the target path already exists as a directory/non-file path. **Run Selected**: fires only the selected node(s) simultaneously without any fan-out to children. **Run From Here**: fires the single selected node and propagates to all its descendants. `MainWindow` calls `PropertiesPanel.commit_pending_edits()` before all run modes and before Save Workflow; the panel also commits pending edits before switching to a different node. Load/Clear hide the panel before destructive canvas updates, commit handlers skip missing/non-live node IDs, and workflow load surfaces parse/schema errors through an error dialog instead of crashing. Workflow payload parsing is atomic: parse/validate first, then clear/apply only on success, so invalid files do not wipe the current canvas. A malformed node record (bad structure, failed deserialization, or duplicate ID) aborts the entire load; malformed connection records are silently dropped because a partial connection set is still a coherent graph. This keeps execution/serialization aligned with the latest visible panel edits and prevents stale panel commits from targeting replaced/deleted nodes. The Start-root restriction applies only to Run All.

## Built-In Models
- Claude: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex: GPT-5.3 Codex with `low`, default (medium), `high`, and `xhigh` reasoning effort.
- Gemini: model catalog defined in `src/llm/gemini_provider.py`.

## User Data and Artifacts
- Workflow graphs are user-saved JSON files chosen from File → Save/Load Workflow dialogs. Workflow files are saved wherever the user chooses (not necessarily in the project folder).
- `saves/*.json` holds tracked workflow fixtures used for manual/testing scenarios.
- Node output is held in-memory during runtime and displayed in the `PropertiesPanel` for the currently selected node.
- All LLM subprocess calls run with the selected project folder as their working directory (`cwd`).
- Recently opened project folders are stored in `.recent_folders.json` at the repo root (gitignored).

## Change Map
- App startup and entrypoint behavior: `workflow_entry.py`, `run_gui_workflow.bat`.
- Canvas graph behavior and workflow execution order: `src/gui/canvas.py`.
- Workflow save/load serialization, payload validation, and provider registry lookup: `src/gui/workflow_io.py`.
- Node rendering, animated status glow, and node graph item behavior: `src/gui/llm_node.py`.
- File operation nodes (create/truncate/delete file, synchronous execution): `src/gui/file_op_node.py`.
- Sliding properties panel (node name, model, prompt, filename, output): `src/gui/properties_panel.py`.
- Model selector dropdown and provider icon rendering: `src/gui/llm_widget.py`, `src/gui/assets/`.
- Save/load and toolbar actions: `src/gui/main_window.py`.
- Provider models and CLI command construction: `src/llm/*_provider.py`.
- Subprocess streaming, cancellation, and timeouts: `src/workers/llm_worker.py`.
