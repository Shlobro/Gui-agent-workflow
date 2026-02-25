# gui Developer Guide

## Purpose
Implements the interactive Qt UI for composing and running LLM workflows.

## Contents
- `main_window.py`: Main shell (toolbar, status bar, save/load/clear actions) and `WorkflowCanvas` host.
- `canvas.py`: `QGraphicsView` orchestration, pan/zoom controls, connection creation, run sequencing, prompt variable resolution, and workflow save/load serialization.
- `bubble_node.py`: Node rendering, embedded widget editor, compact provider-badged model selector with top-level overlay dropdown, port positions, status color, and per-node output panel.
- `connection_item.py`: Directed Bezier edge with optional "inject output" behavior flag.
- `connection_dialog.py`: Connection configuration dialog shown when creating edges.
- `__init__.py`: Package marker.

## Key Interactions
- `WorkflowCanvas` owns node/edge lifecycle and triggers sequential execution.
- `WorkflowCanvas` creates `LLMWorker` instances and routes streamed output into the active `BubbleNode`.
- `BubbleNode` holds user-editable metadata (title, prompt, model) used by execution and save/load.
- `MainWindow` delegates all graph behavior to the canvas and focuses on app-level controls.

## Behavior Notes
- Only acyclic subgraphs are executable; cycles are blocked with an error dialog.
- Running from selection executes the reachable subgraph from that node.
- Prompt placeholders support `{{prev_output}}` plus upstream aliases (bubble id, label index, normalized title, `bubble_<index>`).
- Model selection uses a compact selector row that opens a top-level overlay dropdown (not a Qt popup window), keeps node height unchanged while open, clamps dropdown geometry to visible window bounds (opening upward when needed), shows per-provider badges (Anthropic/OpenAI/Gemini), auto-selects the first available model, and lazy-loads provider modules if needed.
