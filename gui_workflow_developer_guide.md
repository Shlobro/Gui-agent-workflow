# GUI Workflow Developer Guide (Repo Root)

## Purpose
GUI Workflow is a PySide6 desktop application for building and executing node-based LLM workflows. Users create "bubbles", connect them from a permanent Start node, and run the resulting trigger-driven graph.

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
4. Canvas interactions create nodes/connections, support wheel zoom and right-drag panning, allow left-drag rubber-band multi-selection, render selected bubbles with a light-blue neon frame, keep background grid dots visible with fixed on-screen size across zoom levels, auto-expand scene bounds so corner nodes remain reachable, route connection lines around bubble bounds (including immediate reroute right after connection creation), keep arrowheads visible by ending slightly before the input port center, show direction cues on ports with ingress/egress arrows that protrude from the bubble edges and hide once that side is connected, expose an expanded connection hit area so arrow selection is easier, suspend wheel zoom while model dropdowns are open so wheel input scrolls the model list, and optionally save/load workflow JSON files.
5. Three run modes are available. **Run All**: starts from the permanent Start node, validates all reachable nodes (aborts with a warning on missing prompt or model), then fires Start's direct children; each node fires its own children on successful completion via `LLMWorker`. **Run Selected**: fires only the selected node(s) simultaneously without any fan-out to children. **Run From Here**: fires the single selected node and propagates to all its descendants. The Start-root restriction applies only to Run All.

## Built-In Models
- Claude: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex: GPT-5.3 Codex with `low`, default (medium), `high`, and `xhigh` reasoning effort.
- Gemini: model catalog defined in `src/llm/gemini_provider.py`.

## User Data and Artifacts
- Workflow graphs are user-saved JSON files chosen from file dialogs.
- Node output is held in-memory during runtime and displayed in each node.
- Codex runs may write `.codex_last_message.txt` inside a configured working directory when that path is passed to the provider.

## Change Map
- App startup and entrypoint behavior: `workflow_entry.py`, `run_gui_workflow.bat`.
- Canvas graph behavior and workflow execution order: `src/gui/canvas.py`.
- Node rendering, node editor behavior, and viewport-anchored overlay provider-logo model picker behavior: `src/gui/bubble_node.py`, `src/gui/assets/`.
- Save/load and toolbar actions: `src/gui/main_window.py`.
- Provider models and CLI command construction: `src/llm/*_provider.py`.
- Subprocess streaming, cancellation, and timeouts: `src/workers/llm_worker.py`.
