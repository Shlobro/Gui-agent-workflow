# GUI Workflow Developer Guide (Repo Root)

## Purpose
GUI Workflow is a PySide6 desktop application for building and executing node-based LLM workflows. Users create "bubbles", connect them, and run the resulting DAG in topological order.

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
3. `src.gui.main_window.MainWindow` creates the toolbar/status shell and mounts `WorkflowCanvas`.
4. Canvas interactions create nodes/connections and optionally save/load workflow JSON files.
5. Execution resolves prompt placeholders, chooses the provider for each model, and runs each node via `LLMWorker`.

## User Data and Artifacts
- Workflow graphs are user-saved JSON files chosen from file dialogs.
- Node output is held in-memory during runtime and displayed in each node.
- Codex runs may write `.codex_last_message.txt` inside a configured working directory when that path is passed to the provider.

## Change Map
- App startup and entrypoint behavior: `workflow_entry.py`, `run_gui_workflow.bat`.
- Canvas graph behavior and workflow execution order: `src/gui/canvas.py`.
- Node rendering, node editor behavior, and bounded overlay provider-logo model picker behavior: `src/gui/bubble_node.py`, `src/gui/assets/`.
- Save/load and toolbar actions: `src/gui/main_window.py`.
- Provider models and CLI command construction: `src/llm/*_provider.py`.
- Subprocess streaming, cancellation, and timeouts: `src/workers/llm_worker.py`.
