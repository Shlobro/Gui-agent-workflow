# gui Developer Guide

## Purpose
Implements the interactive Qt UI for composing and running LLM workflows.

## Contents
- `main_window.py`: Main shell with File/Prompt menus, toolbar, and status bar. Hosts `WorkflowCanvas` and `PropertiesPanel` in a horizontal `QSplitter`, restores and saves panel width plus panel text zoom with `QSettings`, loads/saves prompt-injection templates via `PromptInjectionStore`, applies default or next-run prompt injections before each run, and resolves template placement (`prepend`/`append`) plus one-off placement when building run payloads for the canvas, drives the panel from `canvas.selection_changed`, commits pending edits before run/save operations, hides the panel before destructive canvas mutations, catches load parse/schema errors for a user-facing dialog, listens for `canvas.usage_limit_hit`, defines the app-wide rounded `QScrollBar` theme (18 px capsule rail with inset bordered capsule handles), and uses non-native `QFileDialog` pickers for Save/Load so app styling applies consistently.
- `dialogs/`: Modal dialog classes for runtime user notifications and prompt-injection setup.
- `canvas/` subpackage: Houses `WorkflowCanvas` and its mixins.
- `llm_node.py`: Shared graphics-item base plus `LLMNode` and `StartNode`.
- `llm_widget.py`: `ModelSelector`, model list widget, provider icon helpers, and `populate_model_selector`. The model dropdown list keeps its own stylesheet, including local scrollbar rules matching the app theme.
- `file_op_node.py`: `FileOpNode` plus convenience factories and `AttentionNode`. File-op operation type lives on the node instance. `AttentionNode` stores `message_text` and serializes as `node_type: "attention"`.
- `git_action_node.py`: Compact node for git operations with action/message settings.
- `_panel_forms.py`: Form widget classes (`_LLMForm`, `_FileOpForm`, `_ConditionalForm`, `_LoopForm`, `_GitActionForm`, `_AttentionForm`) used by `PropertiesPanel`. `_ConditionalForm` hides filename controls for project-scoped conditions and shows their note text. `_LLMForm` uses a vertical splitter for editors/output; within the prompt area it uses a nested vertical splitter to show editable Prompt text above a read-only Prompt Preview.
- `properties_panel.py`: Resizable side panel containing `_LLMForm` (page 1), `_FileOpForm` (page 2), `_ConditionalForm` (page 3), `_LoopForm` (page 4), `_GitActionForm` (page 5), and `_AttentionForm` (page 6). Emits `title_committed`, `model_changed`, `prompt_committed`, `filename_committed`, `attention_message_committed`, `op_type_changed`, `condition_type_changed`, `loop_count_changed`, `git_action_changed`, and `text_zoom_changed`. `MainWindow` listens to `text_zoom_changed` to persist the zoom level. `msg_source`, `commit_msg`, `commit_msg_file`, and `message_text` write directly to node attrs without undo commands. Also tracks preferred width, applies Ctrl+mouse-wheel text zoom, exposes `maybe_append_output`, `maybe_clear_output`, and `refresh_if_current(node)`, defines a panel-local scrollbar style for its scroll areas/editors, and renders a live Prompt Preview for the selected LLM node using the same template/one-off composition pipeline as execution (plain concatenated text with no bracketed section markers).
- `workflow_io.py`: Pure serialization and validation helpers. `parse_workflow_data` validates and normalizes payloads; malformed node records abort the load, malformed connections are dropped.
- `conditional_node.py`: `ConditionalNode` with true/false output ports. `CONDITION_REGISTRY` maps condition IDs to metadata dicts containing `display_name`, `requires_filename`, `execution_mode` (`"sync"` or `"git_worker"`), `note`, and optionally `evaluator` for synchronous conditions. Built-in conditions are `file_empty` (sync, requires filename) and `git_changes` (git_worker, no filename). `git_changes` runs `git status --porcelain --untracked-files=all` against the selected project folder in a background `GitWorker` with streamed git output and a 15-second timeout. Adding a new async condition requires a dedicated execution path in `_fire_condition_check`; setting `execution_mode: "git_worker"` alone routes to the git-status path, not a generic worker factory.
- `loop_node.py`: `LoopNode` with loop/done output ports and loop-token keyed counters. The `loop` branch fires exactly `loop_count` times for a loop thread; the `done` branch fires on the next re-entry after the final loop pass.
- `connection_item.py`: Directed edge item carrying `source_port` for multi-port nodes.
- `undo_commands.py`: `QUndoCommand` implementations for graph mutations.
- `project_chooser.py`: Startup dialog for selecting the project folder and persisting recent folders. Uses its own stylesheet including rounded scrollbar styling for the recent-folder list, and opens folder selection with non-native `QFileDialog` options so dialog scrollbars follow the app theme.
- `assets/`: Static logo files used by the model selector.
- `__init__.py`: Package marker.

## Key Interactions
- `WorkflowCanvas` owns node and edge lifecycle and triggers execution. For Run All, `StartNode` is the root and its direct children fire first. LLM nodes execute via `LLMWorker`; git nodes execute via `GitWorker`; file-op, attention, and loop nodes execute synchronously; `git_changes` condition checks also execute via `GitWorker` while other condition evaluators stay synchronous, and they stream git output into the conditional node before the terminal success/error event. Successful completion queues downstream triggers through the Qt event loop so recursion stays shallow and each deferred callback re-checks that the source-to-target edge still exists. `stop_all()` cancels LLM and git workers.
- Before any run, reachable nodes are validated with node-type rules: `LLMNode` requires a prompt and a registered model; `FileOpNode` requires a filename; `ConditionalNode` requires a known `condition_type` and a filename only for filename-scoped conditions; `AttentionNode` requires a non-empty message; `LoopNode` has no extra validation beyond valid `loop_count`; `GitActionNode` requires valid action/source enums plus the appropriate commit-message input for `git_commit`.
- `MainWindow` maps panel signals to canvas undo handlers or direct content writes. `filename_committed` is reused for both `FileOpNode` and filename-scoped `ConditionalNode` edits. `attention_message_committed` writes `AttentionNode.message_text` directly.
- `MainWindow` persists panel width after user splitter moves and when the panel is hidden; text zoom is persisted on each Ctrl+wheel change via `text_zoom_changed`.
- Prompt injections are configured from the Prompt menu. Persistent template defaults and per-template placement come from `PromptTemplateManagerDialog`; per-run overrides come from `PromptInjectionRunDialog`, including one-off placement; resolved prepend/append template content plus one-off payload is pushed to `WorkflowCanvas` before each run command.
- Per-run injection overrides are consumed when a run actually starts (`run_state_changed(True)`), not when run is merely requested. While a run is active, preview uses the active run payload so one-off context remains visible until run completion.
- The LLM form preview mirrors the current node prompt text (no template or one-off injection blocks). It updates while typing in the Prompt editor.
- `LLMNode`, `FileOpNode`, `ConditionalNode`, `AttentionNode`, and `GitActionNode` store their user-editable fields as plain Python attributes. Canvas execution and serialization read those attributes directly.

## Behavior Notes
- The Start node is permanent and recreated after Clear Canvas. Its position is saved and restored with workflow JSON.
- Cyclic graphs execute continuously until the user stops the workflow. Drawing a connection that would create a cycle still warns first, but the user may proceed.
- Loop bodies require an explicit feedback edge into the loop node input (for example `Loop(loop) -> Body -> Loop(input)`) so the next pass can re-enter the loop node.
- All non-start workflow nodes share the same timer-driven active-border animation while their status is `running` (or `looping` for loop nodes), and selected active nodes use a stronger pulsing selection ring derived from the active status color.
- Loop nodes use status `looping` during in-progress iterations (amber visual treatment) and switch to `done` (green) only on final completion.
- Nodes not reachable from Start are never executed by Run All.
- Children fire only on successful completion.
- Run Selected fires only the selected node(s) without triggering children. Run From Here fires the selected node and all descendants reachable from it.
- Mouse wheel zoom is active on the canvas except while a model dropdown is open.
- Ctrl+mouse-wheel inside the properties panel changes the panel text size instead of the canvas zoom.
- Canvas panning uses right-button drag; left-drag on empty canvas draws a rubber-band selection rectangle.
- Connection paths route around node bounds for all built-in node types, and connection items use an expanded hit-test shape.
- Copy/paste includes `LLMNode`, `FileOpNode`, `ConditionalNode`, `AttentionNode`, `LoopNode`, and `GitActionNode` but excludes Start.
- Conditional nodes serialize `condition_type` and `filename`. `git_changes` evaluates the selected project folder instead of a node filename in a background `GitWorker`, streams git output into the node log, and raises a timeout error after 15 seconds if git hangs.
- Attention nodes serialize `name` and `message`. Save/load accepts empty messages so workflows remain reloadable; run-time validation still blocks execution until the message is filled in.
- Properties panel output areas stream execution output for the currently selected node.
