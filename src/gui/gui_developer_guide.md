# gui Developer Guide

## Purpose
Implements the interactive Qt UI for composing and running LLM workflows.

## Contents
- `main_window.py`: Main shell with File/Prompt menus, toolbar, and status bar. Hosts `WorkflowCanvas` and `PropertiesPanel` in a horizontal `QSplitter`, restores and saves panel width and panel text zoom with `QSettings`, keeps the side panel permanently visible, drives node-vs-overview mode from `canvas.selection_changed`, applies prompt injections before each run, and handles save/load/clear/project-folder flows. It also handles usage-limit dialogs and the run-time prompt that appears when a loaded workflow already contains saved LLM sessions.
- `llm_sessions/`: Helper package for workflow-overview rendering, LLM form session-widget loading, and workflow-level named-session rules. See `llm_sessions/llm_sessions_developer_guide.md` for its local developer guide.
- `dialogs/`: Modal dialog classes for runtime user notifications and prompt-injection setup.
- `canvas/` subpackage: Houses `WorkflowCanvas` plus execution, IO, subprocess, and named-session state mixins.
- `control_flow/`: Coordination-oriented nodes such as `JoinNode`.
- `llm_node.py`: Shared graphics-item base plus `LLMNode` and `StartNode`. `WorkflowNode` carries `is_invalid`; invalid nodes render a red border while not actively running or looping.
- `checked_dropdown.py`: Reusable checked popup dropdown used by per-node prompt-template selection controls.
- `llm_widget.py`: `ModelSelector`, model list widget, provider icon helpers, and `populate_model_selector`.
- `file_op_node.py`: `FileOpNode` plus convenience factories and `AttentionNode`.
- `git_action_node.py`: Compact node for git operations with action/message settings.
- `_panel_forms.py`: Form widget classes used by `PropertiesPanel`.
- `properties_panel.py`: Resizable side panel with `_OverviewForm`, per-node forms, and the LLM Prompt/Output tabs. The stacked panel switches among overview, LLM, file-op, conditional, loop, join, git-action, attention, and script forms. The LLM form owns the model selector, the session controls, prompt preview, and per-call output tabs.
- `workflow_io.py`: Pure serialization and validation helpers.
- `conditional_node.py`: `ConditionalNode` and condition registry metadata.
- `loop_node.py`: `LoopNode` with loop/done output ports.
- `control_flow/join_node.py`: `JoinNode`, a barrier node that waits for a configured number of arrivals before releasing once.
- `script_runner/`: Script execution node package with `ScriptNode`.
- `connection_item.py`: Directed edge item carrying `source_port`, optional manual bend vertices, and connection-segment/handle hit targets for vertex editing.
- `undo_commands.py`: `QUndoCommand` implementations for graph mutations.
- `project_chooser.py`: Startup dialog for selecting and persisting project folders.
- `assets/`: Static logo files used by the model selector.

## Key Interactions
- The panel remains visible at all times. With exactly one selected workflow node it shows that node form; with exactly one selected connection it shows an arrow-focused overview; otherwise it shows the workflow overview page.
- Overview data is maintained by `MainWindow` and includes working directory, connection count, selected counts, node counts by type, invalid node titles, prompt injection payload, resumable LLM count, and saved-session count.
- Before any run, reachable nodes are validated with node-type rules (`LLMNode`, `FileOpNode`, `ConditionalNode`, `AttentionNode`, `LoopNode`, `JoinNode`, `GitActionNode`, `ScriptNode`).
- The same validation rules drive live node highlighting: invalid nodes get a red border until required fields are valid.
- Prompt injection preview in selected LLM forms stays aligned with the current preview or active run context plus the selected node's saved prepend/append template overrides.
- `JoinNode` is a barrier: it waits for `wait_for_count` arrivals from the same parallel split group before it releases one downstream continuation.

## LLM Session UI Rules
- Claude and Codex/OpenAI models show three controls: `Resume previous session`, `Save session ID`, and `Resume session ID`.
- Gemini hides the entire session-controls block and any hidden session settings are cleared during reconciliation.
- `Resume previous session` remains node-local and undoable.
- `Save session ID` reserves a workflow-level name for the current node. The name is typed by the user and can only be owned by one node at a time.
- `Resume session ID` only lists names that already have a captured session ID, match the selected node's provider, and come from a save-owner node that can reach the current node through the graph.
- Connection edits while an LLM node is selected must refresh that dropdown immediately; the user should not need to reselect the node after wiring a newly valid upstream path.
- Selecting `Resume session ID` disables named-session saving on that node because the resumed named conversation becomes the active session source.
- Changing a node's model while it owns saved session data prompts first; on confirmation, incompatible saved session IDs are cleared and named-session references are reconciled.
- Loading a workflow with saved node or named sessions does not prompt immediately. The prompt appears only when the user starts a run.
- Choosing `Start Fresh` on that prompt clears all captured node and named session IDs from the in-memory workflow.

## Behavior Notes
- The Start node is permanent and recreated after Clear Canvas.
- Run Selected fires only selected node(s) without fan-out. Run From Here fires the selected node and descendants.
- Usage-limit dialogs can schedule auto-resume from the failed node. A scheduled auto-resume is canceled if any workflow run starts before the timer fires.
- Mouse-wheel zoom is active on canvas except while the model dropdown is open.
- Selected connections expose bend handles. Double-click a segment to add a vertex, drag a handle to move it, and Shift+click a handle to remove it.
- Manual connection vertices are persisted in workflow JSON as `connections[].vertices` and participate in undo/redo, paste, and load flows.
- LLM output logs include per-invocation separators (`=== Call N ===`), and the LLM output pane renders those separators as separate nested `Call N` tabs.
- Workflow-named LLM sessions share one in-memory output history across the save-owner and every resume node using that same session name; each call block includes the producing node title, the session label, the full composed prompt, and then the response content.
- Each `LLMNode` has checked `Prepend` and `Append` dropdowns listing every saved prompt template. Saved global default templates appear selected in both dropdowns by default; the node stores only local additions and per-side opt-outs from that default set, while prompt preview can still reflect transient next-run injection state.
- Ctrl+mouse-wheel inside properties panel changes panel text size.
- Properties panel output areas stream execution output for the currently selected node.
- Copy/paste generates a new node identity and never carries over a saved Claude/Codex session ID or named-session binding to the pasted node.
