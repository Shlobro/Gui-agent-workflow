# canvas Developer Guide

## Purpose
The `canvas/` subpackage houses `WorkflowCanvas` and its two behaviour mixins. Splitting into three files keeps each under 1000 LOC while keeping `WorkflowCanvas` as the single public class — external imports use `from src.gui.canvas import WorkflowCanvas`; internal `src/gui` modules typically use `from .canvas import WorkflowCanvas`.

## Files
- `__init__.py`: `WorkflowCanvas(_ExecutionMixin, _IOMixin, QGraphicsView)` — orchestration only. Owns `__init__`, background grid, start-node creation, node/connection CRUD (`add_llm_node`, `add_file_op_node`, `add_conditional_node`, `remove_node`), panel commit handlers (`_on_title_editing_finished`, `_on_model_changed`, `_on_op_type_changed`, `_on_condition_type_changed`), mouse/keyboard/wheel event handlers, and connection drawing. Connection drawing tracks `_conn_source_port` to identify which output port the drag started from; `ConditionalNode` gets priority detection for its `true`/`false` ports before the generic `is_near_output_port` scan.
- `execution.py`: `_ExecutionMixin` — all run/stop logic. Contains `run_all`, `run_selected_only`, `run_from_here`, `stop_all`, graph-traversal helpers (`_reachable_from`, `_would_create_cycle`, `_source_port_has_outgoing`, `_validate_nodes`, `_direct_children`), and the invocation engine (`_run_workflow`, `_trigger_node`, `_fire_invocation`, `_fire_file_op`, `_fire_condition_check`, `_on_condition_done`, `_resolve_file_op_path`, `_queue_child_triggers`, `_trigger_node_if_active`, `_on_invocation_done`, `_check_drain`). `_fire_condition_check` evaluates a `ConditionalNode` synchronously and routes via `_on_condition_done`. `_queue_child_triggers` accepts an optional `branch` parameter; for `ConditionalNode` only connections whose `source_port` matches `branch` are queued.
- `io.py`: `_IOMixin` — graph mutation primitives and persistence. Contains undo helpers called by `QUndoCommand` subclasses (`_undo_add_node`, `_undo_remove_node`, `_undo_add_connection`, `_undo_remove_connection_item`, `_find_connection`), clipboard (`_copy_selected`, `_paste`), `clear_canvas`, and `get_workflow_data` / `load_workflow_data`. `_undo_add_connection` and `_find_connection` both accept a `source_port` parameter (default `"output"`) to distinguish connections on multi-port nodes like `ConditionalNode`.

## Mixin Pattern
`_ExecutionMixin` and `_IOMixin` are not standalone — they access `WorkflowCanvas` instance attributes (`self._nodes`, `self._scene`, etc.) freely. The `TYPE_CHECKING` guard imports `WorkflowCanvas` in each mixin only for type-checker annotations; no runtime circular import occurs.

## Key Invariants
- All undo-pushable mutations go through `WorkflowCanvas._undo_stack`.
- `_undo_in_progress` is set `True` inside every `QUndoCommand.redo/undo` that touches node attributes, so the panel commit handlers don't re-push duplicate commands.
- `notify_node_changed(node_id)` re-emits `selection_changed` after undo/redo attribute changes so the properties panel refreshes automatically.
