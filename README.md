# GUI Workflow

A visual node-graph editor for chaining LLM calls, file operations, git actions, scripts, and control-flow nodes in a desktop PySide6 app.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.7+-green?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

---

![screenshot](screen%20shot/screenshot%201.png)

---

## What It Does

Build workflows visually. Connect nodes. Run them.

Each node does one job. LLM nodes call Claude, Codex/OpenAI, or Gemini. Other nodes handle files, conditions, loops, joins, git actions, attention pauses, and scripts.

## Node Types

| Node | What it does |
|------|-------------|
| **LLM** | Calls Claude, Gemini, or Codex with a prompt. Claude/Codex nodes can optionally resume their previous session context. |
| **File Op** | Creates, truncates, or deletes a file in the project folder. |
| **Conditional** | Evaluates a condition and routes to a true or false branch. |
| **Attention** | Stops on that branch and asks the user whether to continue. |
| **Loop** | Fires its loop port N times, then fires its done port once. |
| **Join** | Waits for a configured number of arrivals before releasing one continuation. |
| **Git Action** | Runs `git add`, `git commit`, or `git push`. |
| **Script** | Runs a project-relative `.bat`, `.cmd`, or `.ps1` script. |
| **Start** | The permanent root node. Run All always begins here. |

## Supported LLMs

| Provider | Models |
|----------|--------|
| **Claude** | Opus 4.6, Sonnet 4.6, Haiku 4.5 |
| **Codex / OpenAI** | GPT-5.4 and GPT-5.3 Codex with `low` / `medium` / `high` / `xhigh` effort |
| **Gemini** | Gemini 3.1 Pro, Gemini 3 Flash, Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.5 Flash Lite |

All providers run as CLI subprocesses.

`Resume previous session` is available only for Claude and Codex/OpenAI models. If a Gemini model is selected, the checkbox is disabled and cleared.

## Getting Started

```bash
pip install PySide6
python workflow_entry.py
```

Or launch `run_gui_workflow.bat` on Windows.

On first launch, choose a project folder. LLM, git, and script subprocesses run with that folder as their working directory.

## Run Modes

| Mode | What runs |
|------|-----------|
| **Run All** | Validates the reachable graph from Start and runs it. |
| **Run Selected** | Runs only the selected node(s) without fan-out. |
| **Run From Here** | Runs the selected node and its descendants. |

## LLM Session Resume

When `Resume previous session` is enabled on an LLM node:

- The first Claude/Codex call starts fresh and stores the returned session ID in the workflow JSON.
- Later calls from that same node automatically resume the saved session so the model keeps context.
- If the same resumable node is reached in parallel, later invocations wait until the earlier one finishes so the conversation stays linear.
- If you load a workflow that already contains saved LLM sessions, the next run asks whether to resume those saved sessions or delete them and start fresh.
- If you change the model on a node that already has a saved Claude/Codex session, the app warns first. Approving the change deletes that node's saved session.
- Copy/paste does not clone a live Claude/Codex session. Pasted LLM nodes start with no saved provider session ID.

## Canvas Controls

| Action | How |
|--------|-----|
| Add node | Toolbar buttons |
| Connect nodes | Drag from an output port to an input port |
| Select multiple | Left-drag rubber-band |
| Pan | Right-drag |
| Zoom | Mouse wheel |
| Edit node | Select it and use the Properties Panel |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Y` |
| Copy / Paste | `Ctrl+C` / `Ctrl+V` |
| Delete | `Delete` or `Backspace` |

## Saving Workflows

`File -> Save Workflow` writes a `.json` file you can reload later.

The JSON stores:

- `nodes[]`
- `connections[]`
- `node_counter`
- `start_pos`

LLM nodes can also store:

- `resume_session_enabled`
- `save_session_enabled`
- `save_session_name`
- `resume_named_session_name`
- `saved_session_id`
- `saved_session_provider`

Workflow JSON can also store:

- `named_sessions[]`

## Project Structure

```text
GUI Workflow/
|-- workflow_entry.py
|-- run_gui_workflow.bat
|-- requirements.txt
`-- src/
    |-- llm/
    |-- workers/
    `-- gui/
        |-- canvas/
        |-- dialogs/
        |-- main_window.py
        |-- llm_node.py
        |-- file_op_node.py
        |-- conditional_node.py
        |-- loop_node.py
        |-- git_action_node.py
        |-- connection_item.py
        |-- properties_panel.py
        `-- _panel_forms.py
```

## Requirements

- Python 3.11+
- PySide6 >= 6.7.0
- CLI tools installed for the providers you want to use: `claude`, `codex`, `gemini`
