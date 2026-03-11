# canvas Developer Guide

## Purpose
The `canvas/` subpackage houses `WorkflowCanvas` and its two behavior mixins. Splitting it into three files keeps each under 1000 LOC while preserving `WorkflowCanvas` as the single public class.

## Files
- `__init__.py`: `WorkflowCanvas(_ExecutionMixin, _IOMixin, QGraphicsView)` owns initialization, background grid, start-node creation, node/connection CRUD (`add_llm_node`, `add_file_op_node`, `add_git_action_node`, `add_conditional_node`, `add_attention_node`, `add_loop_node`, `remove_node`), panel commit handlers, mouse/keyboard/wheel event handling, connection drawing, `_loop_counters`, `_exec_lineage`, and run-scoped prompt-injection state set by `MainWindow` via `set_prompt_injections(...)` (separate prepend/append template buckets plus one-off placement). The view uses `AnchorUnderMouse` for zoom (wheel/pinch) and `AnchorViewCenter` for resize events. Panel open/close recentering is handled by `MainWindow` via `_show_panel()`, `_hide_panel()`, and `_restore_panel_width_and_recenter()`, which snapshot and restore the scene center around splitter size changes.
- `execution.py`: `_ExecutionMixin` contains run/stop logic, graph traversal, validation, and the invocation engine (`_fire_invocation`, `_fire_file_op`, `_fire_git_action`, `_fire_condition_check`, `_fire_attention`, `_fire_loop`). `_validate_nodes` requires non-empty messages for `AttentionNode` and only requires conditional filenames for condition types that declare `requires_filename`. Loop invocations use status `looping` while iterating, route the `loop` branch exactly `loop_count` times for a loop thread, and route `done` on the next re-entry. `_fire_condition_check` resolves filenames only when needed. `git_changes` evaluates against the selected project folder in a background `GitWorker`, streams git output into the conditional node log, and aborts with a timeout error after 15 seconds if git does not return. LLM invocations call `compose_prompt(...)` so enabled templates and one-off context are placed deterministically on prepend/append sides of the base prompt. Usage-limit detection also treats Claude CLI quota text in the form `You've hit your limit · resets ...`, OpenAI-style `rate limit reached for requests` / `You exceeded your current quota`, Anthropic-style `rate_limit_error`, and Gemini-style `RESOURCE_EXHAUSTED` quota text as usage-limit events so the dialog flow still triggers.
- `io.py`: `_IOMixin` contains graph mutation primitives, clipboard, `clear_canvas`, and `get_workflow_data` / `load_workflow_data`. Connection helpers accept `source_port` so multi-port node edges are preserved.

## Mixin Pattern
`_ExecutionMixin` and `_IOMixin` are not standalone. They rely directly on `WorkflowCanvas` instance state and use `TYPE_CHECKING` imports only for annotations.

## Key Invariants
- All undo-pushable mutations go through `WorkflowCanvas._undo_stack`.
- `_undo_in_progress` is set during undo/redo mutations so panel commit handlers do not push duplicate commands.
- `notify_node_changed(node_id)` re-emits `selection_changed` after undo/redo attribute changes so the properties panel refreshes automatically.

## Attention And Git-Change Conditions
- `WorkflowCanvas.add_attention_node()` creates `AttentionNode` snapshots with a user-facing `message` field so save/load, undo, and paste treat the node like any other built-in node type.
- `_ExecutionMixin._fire_attention()` opens a modal `QMessageBox` (nested Qt event loop — other branches and background workers keep running) and fans out only when the user clicks Continue. It is a single-branch gate, not a global pause.
- `_ExecutionMixin._fire_condition_check()` resolves a file path only when `condition_requires_filename(condition_type)` is true, then dispatches based on `condition_execution_mode(condition_type)`: `"git_worker"` conditions are routed to `_fire_git_changes_condition()`, which runs `git status --porcelain --untracked-files=all` with a 15-second timeout; `"sync"` conditions call `node.evaluate()` on the UI thread. Adding a new async condition type requires both a registry entry with `execution_mode: "git_worker"` and a dedicated execution path in `_fire_condition_check`; the current engine does not auto-dispatch arbitrary worker strategies from registry data alone.

