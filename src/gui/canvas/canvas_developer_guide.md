# canvas Developer Guide

## Purpose
The `canvas/` subpackage houses `WorkflowCanvas` and its three behavior mixins. Splitting it into four files keeps each under the file-size cap while preserving `WorkflowCanvas` as the single public class.

## Files
- `__init__.py`: `WorkflowCanvas(_SubprocessExecutionMixin, _ExecutionMixin, _SessionStateMixin, _IOMixin, QGraphicsView)` owns initialization, background grid, start-node creation, node and connection CRUD, panel commit handlers, mouse and keyboard event handling, connection drawing, connection-vertex editing interactions, prompt-injection state, and the undo stack.
- `execution.py`: `_ExecutionMixin` contains run/stop logic, graph traversal, validation, and the core invocation engine (`_fire_invocation`, `_fire_condition_check`, `_fire_attention`, `_fire_loop`, `_fire_join`). It also owns usage-limit detection, LLM call headers, session capture persistence, and serialization for any resumed LLM conversation key (node-local or workflow-named).
- `llm_output.py`: Shared helpers for mirroring named-session output across related LLM nodes and for building the per-call node/session/prompt metadata block that appears before each response.
- `llm_resume.py`: Helpers for resolving the effective resume session ID / serialization key for LLM calls and for draining queued named-session resumptions one at a time.
- `session_state.py`: `_SessionStateMixin` owns workflow-level named-session storage, node-session snapshot helpers, save/resume option filtering, and named-session reconciliation.
- `subprocess_execution.py`: `_SubprocessExecutionMixin` owns project-relative path confinement plus file-op, git-action, and script-runner execution.
- `io.py`: `_IOMixin` contains graph mutation primitives, clipboard, `clear_canvas`, and `get_workflow_data` / `load_workflow_data`.

## Mixin Pattern
- `_SubprocessExecutionMixin`, `_ExecutionMixin`, `_SessionStateMixin`, and `_IOMixin` are not standalone. They rely directly on `WorkflowCanvas` instance state and use `TYPE_CHECKING` imports only for annotations.

## Key Invariants
- All undo-pushable mutations go through `WorkflowCanvas._undo_stack`.
- `_undo_in_progress` is set during undo/redo mutations so panel commit handlers do not push duplicate commands.
- `notify_node_changed(node_id)` re-emits `selection_changed` after undo/redo attribute changes so the properties panel refreshes automatically.
- `refresh_node_validation_state()` applies run-validation rules to all non-start nodes and toggles each node's invalid flag; invalid nodes render with a red border until required fields are fixed.
- `_pending_join_waits` must stay in sync with `_join_wait_counts`; otherwise `_check_drain()` can incorrectly mark a workflow complete while join barriers are still waiting.

## LLM Session Resume Rules
- LLM node JSON can persist `resume_session_enabled`, `save_session_enabled`, `save_session_name`, `resume_named_session_name`, `saved_session_id`, and `saved_session_provider`.
- Workflow JSON also persists `named_sessions`, a workflow-level name-to-session store keyed by user-defined names.
- `load_workflow_data()` normalizes unsupported session state away for non-resumable providers and reconciles stale named-session references after nodes and connections are restored.
- `WorkflowCanvas.has_saved_llm_sessions()` and `clear_all_llm_sessions()` cover both node-local saved sessions and workflow-level named sessions for the main-window run prompt.
- `execution.py` serializes concurrent invocations that reuse the same conversation key. Node-local resume uses `node:<node_id>` and named-session resume uses `named:<session_name>`.
- Named-session resume is only valid when the saved session already has a captured ID, matches the current provider, and the graph still has a path from the owner node to the current node.
- When a connection add/remove/undo/redo changes graph reachability, selected LLM nodes must refresh their session dropdown immediately so newly valid named sessions appear without reselection.
- Queued resumable LLM workers are fully signal-wired before they enter the wait queue, so releasing a queue slot only starts the already-connected worker.
- `stop_all()` and node removal clear queued resumable LLM work so shutdown and deletion do not leave orphaned waiting executions behind.
- Copy/paste never preserves provider session IDs or named-session bindings. Pasted LLM nodes keep `resume_session_enabled`, but start with cleared `saved_session_id`, `saved_session_provider`, `save_session_enabled`, `save_session_name`, and `resume_named_session_name`.
- Named-session output is mirrored across all LLM nodes whose effective workflow session name matches, so save-owner and resume nodes display the same merged history. Per-call output blocks include node/session/prompt metadata before response lines.

## Save/Load Notes
- Saved LLM session metadata lives inside the workflow JSON. There is no separate session sidecar file.
- Malformed node records abort load; malformed connections are dropped so a partial graph can still load.
- Connection helpers accept `source_port` so multi-port node edges are preserved, and optional `vertices` so manual bend points survive save/load, undo/redo, and paste.

## Attention, Git, And Script Execution
- `WorkflowCanvas.add_attention_node()` creates `AttentionNode` snapshots with a user-facing `message` field so save/load, undo, and paste treat the node like any other built-in node type.
- `_ExecutionMixin._fire_attention()` opens a modal `QMessageBox` and fans out only when the user clicks Continue. It is a single-branch gate, not a global pause.
- `_ExecutionMixin._fire_condition_check()` resolves a file path only when `condition_requires_filename(condition_type)` is true, then dispatches based on `condition_execution_mode(condition_type)`: `"git_worker"` conditions are routed to `_fire_git_changes_condition()`, which runs `git status --porcelain --untracked-files=all` with a 15-second timeout; `"sync"` conditions call `node.evaluate()` on the UI thread.
- `_SubprocessExecutionMixin._resolve_project_relative_path()` is the shared confinement rule for file ops, git commit-message files, and script paths. Script paths must stay inside the selected project folder and end in `.bat`, `.cmd`, or `.ps1`.
