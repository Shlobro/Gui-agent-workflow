# gui Developer Guide

## Purpose
Implements the interactive Qt UI for composing and running LLM workflows.

## Contents
- `main_window.py`: Main shell with File/Prompt menus, toolbar, and status bar. Hosts `WorkflowCanvas` and `PropertiesPanel` in a horizontal `QSplitter`, restores/saves panel width and panel text zoom with `QSettings`, keeps the side panel permanently visible, drives node-vs-overview mode from `canvas.selection_changed`, updates overview data (working directory, node counts, invalid-node list, prompt injection payload), shows a focused arrow overview when exactly one connection is selected (endpoints + editing shortcuts), applies prompt injections before each run, and handles save/load/clear/project-folder flows. It also handles usage-limit dialogs: users can change model, schedule an automatic resume from the failed node (schedule UI expands only after clicking `Schedule Resume`) via calendar day picker plus clock-style hour/minute dials, or stop workflow.
- `dialogs/`: Modal dialog classes for runtime user notifications and prompt-injection setup.
- `canvas/` subpackage: Houses `WorkflowCanvas` and its mixins.
- `llm_node.py`: Shared graphics-item base plus `LLMNode` and `StartNode`. `WorkflowNode` carries `is_invalid`; invalid nodes render a red border while not actively running/looping.
- `llm_widget.py`: `ModelSelector`, model list widget, provider icon helpers, and `populate_model_selector`.
- `file_op_node.py`: `FileOpNode` plus convenience factories and `AttentionNode`.
- `git_action_node.py`: Compact node for git operations with action/message settings.
- `_panel_forms.py`: Form widget classes used by `PropertiesPanel`.
- `properties_panel.py`: Resizable side panel with `_OverviewForm` (page 0), `_LLMForm` (page 1), `_FileOpForm` (page 2), `_ConditionalForm` (page 3), `_LoopForm` (page 4), `_GitActionForm` (page 5), and `_AttentionForm` (page 6). LLM form uses Prompt/Output tabs, where Prompt contains prompt edit + preview and Output contains the execution log. Exposes `show_overview()` and `set_overview_text(...)` for no-selection state. Emits node edit signals and `text_zoom_changed`.
- `workflow_io.py`: Pure serialization and validation helpers.
- `conditional_node.py`: `ConditionalNode` and condition registry metadata.
- `loop_node.py`: `LoopNode` with loop/done output ports.
- `connection_item.py`: Directed edge item carrying `source_port`, optional manual bend vertices, and connection-segment/handle hit targets for vertex editing.
- `undo_commands.py`: `QUndoCommand` implementations for graph mutations.
- `project_chooser.py`: Startup dialog for selecting/persisting project folders.
- `assets/`: Static logo files used by the model selector.
- `__init__.py`: Package marker.

## Key Interactions
- The panel remains visible at all times. With exactly one selected workflow node it shows that node form; with exactly one selected connection it shows an arrow-focused overview; otherwise it shows the workflow overview page.
- Overview data is maintained by `MainWindow` and includes:
  - Working directory
  - Connection count
  - Selected node count
  - Node counts by type
  - Invalid node count and titles
  - Active prompt injection payload (prepend/append/one-off)
- Before any run, reachable nodes are validated with node-type rules (`LLMNode`, `FileOpNode`, `ConditionalNode`, `AttentionNode`, `LoopNode`, `GitActionNode`).
- The same validation rules drive live node highlighting: invalid nodes get a red border until required fields are valid.
- Prompt injection preview in selected LLM forms stays aligned with current preview/run context.

## Behavior Notes
- The Start node is permanent and recreated after Clear Canvas.
- Run Selected fires only selected node(s) without fan-out. Run From Here fires selected node and descendants.
- Usage-limit dialogs can schedule auto-resume from the failed node. A scheduled auto-resume is canceled if any workflow run starts before the timer fires.
- Mouse wheel zoom is active on canvas except while model dropdown is open.
- Selected connections expose bend handles. Double-click a segment to add a vertex, drag a handle to move it, and Shift+click a handle to remove it.
- Manual connection vertices are persisted in workflow JSON as `connections[].vertices` and participate in undo/redo, paste, and load flows.
- LLM output logs include per-invocation separators (`=== Call N ===`) so repeated loop-triggered calls are easy to distinguish.
- Ctrl+mouse-wheel inside properties panel changes panel text size.
- Properties panel output areas stream execution output for the currently selected node.
