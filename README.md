# GUI Workflow

A visual node-graph editor for chaining LLM calls, file operations, git actions, and control flow — all wired together and executed with a click.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.7+-green?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

---

![screenshot](screen%20shot/screenshot%201.png)

---

## What It Does

Build workflows visually. Connect nodes. Run them.

Each node does one thing — call an LLM, read/write a file, evaluate a condition, loop N times, or run a git command. Connect nodes with arrows and the output of one feeds the input of the next. Hit **Run** and watch it execute.

---

## Node Types

| Node | What it does |
|------|-------------|
| **LLM** | Calls Claude, Gemini, or Codex with a prompt. Output flows downstream. |
| **File Op** | Creates, truncates, or deletes a file in the project folder. |
| **Conditional** | Evaluates a condition (e.g. file empty?) and routes to a true or false branch. |
| **Loop** | Fires its loop port N times, then fires its done port once. |
| **Git Action** | Runs `git add`, `git commit`, or `git push` with configurable message sources. |
| **Start** | The permanent root node. Run All always begins here. |

---

## Supported LLMs

| Provider | Models |
|----------|--------|
| **Claude** | Opus 4.6, Sonnet 4.6, Haiku 4.5 |
| **Codex / OpenAI** | GPT-5.4 and GPT-5.3 — with `low` / `medium` / `high` / `xhigh` reasoning effort |
| **Gemini** | Full model catalog |

All providers are called as CLI subprocesses — prompts delivered via stdin to avoid shell escaping issues.

---

## Getting Started

```bash
pip install PySide6
python workflow_entry.py
```

Or double-click `run_gui_workflow.bat` on Windows.

On first launch, a project chooser dialog lets you pick a working folder. All LLM calls and git operations run with that folder as their `cwd`.

---

## Run Modes

| Mode | What runs |
|------|-----------|
| **Run All** | Validates the full graph, then fires from Start and propagates through all children. |
| **Run Selected** | Fires only the selected node(s) — no fan-out to children. |
| **Run From Here** | Fires the selected node and propagates to all its descendants. |

---

## Canvas Controls

| Action | How |
|--------|-----|
| Add node | Right-click canvas |
| Connect nodes | Drag from an output port to an input port |
| Select multiple | Left-drag rubber-band |
| Pan | Right-drag |
| Zoom | Scroll wheel |
| Edit node | Click to select → Properties Panel slides in from the right |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Y` |
| Copy / Paste | `Ctrl+C` / `Ctrl+V` |
| Delete | `Delete` or `Backspace` |

---

## Saving Workflows

**File → Save Workflow** writes a `.json` file you can reload later. Save anywhere you like.

```
workflow.json
├── nodes[]       — id, type, position, and all node-specific fields
├── connections[] — source, target, source_port
├── node_counter
└── start_pos
```

---

## Project Structure

```
GUI workflow/
├── workflow_entry.py      # Entry point
├── run_gui_workflow.bat   # Windows launcher
├── requirements.txt       # PySide6 only
└── src/
    ├── llm/               # Provider registry + Claude/Gemini/Codex adapters
    ├── workers/           # QThread workers for LLM and git subprocesses
    └── gui/
        ├── canvas/        # WorkflowCanvas, execution engine, undo/clipboard/IO
        ├── dialogs/       # Usage limit dialog and other modal dialogs
        ├── main_window.py # QMainWindow, toolbar, status bar
        ├── llm_node.py    # LLM node item
        ├── file_op_node.py
        ├── conditional_node.py
        ├── loop_node.py
        ├── git_action_node.py
        ├── connection_item.py
        ├── properties_panel.py
        └── _panel_forms.py
```

---

## Requirements

- Python 3.11+
- PySide6 >= 6.7.0
- CLI tools installed for the providers you want to use: `claude`, `gemini`, `codex`
