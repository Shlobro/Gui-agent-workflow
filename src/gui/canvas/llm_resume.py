"""Named-session resume helpers for WorkflowCanvas execution."""

from __future__ import annotations

from src.gui.llm_node import LLMNode


def llm_resume_serial_key(canvas, node: LLMNode) -> str:
    if node.resume_named_session_name:
        record = canvas._named_sessions.get(node.resume_named_session_name.strip())
        if record is not None and record.get("session_id", "").strip():
            return f"named:{node.resume_named_session_name.strip()}"
        return ""
    if node.resume_session_enabled:
        return f"node:{node.node_id}"
    return ""


def llm_resume_session_id(canvas, node: LLMNode, provider_name: str) -> str:
    if node.resume_named_session_name:
        record = canvas._named_sessions.get(node.resume_named_session_name.strip())
        if record is None:
            return ""
        if record.get("provider", "").strip() != provider_name.strip():
            return ""
        return record.get("session_id", "").strip()
    if node.resume_session_enabled:
        return node.saved_session_id.strip()
    return ""


def release_serial_llm_resume_slot(canvas, serial_key: str) -> None:
    if not serial_key:
        return
    canvas._llm_serial_resume_nodes.discard(serial_key)
    queue = canvas._llm_serial_wait_queues.get(serial_key)
    if queue is None:
        return
    while queue:
        _queued_key, exec_id, worker, run_id, _lineage_token, _loop_token, _join_token = queue.pop(0)
        if (
            _queued_key != serial_key
            or run_id != canvas._run_id
            or not canvas._running
            or exec_id not in canvas._current_run_exec_ids
        ):
            canvas._llm_serial_waiting_exec_ids.discard(exec_id)
            canvas._active_workers.pop(exec_id, None)
            canvas._exec_node.pop(exec_id, None)
            canvas._exec_lineage.pop(exec_id, None)
            canvas._exec_streamed_output.pop(exec_id, None)
            canvas._current_run_exec_ids.discard(exec_id)
            continue
        canvas._llm_serial_waiting_exec_ids.discard(exec_id)
        canvas._llm_serial_resume_nodes.add(serial_key)
        canvas._active_workers[exec_id] = worker
        canvas._exec_streamed_output[exec_id] = False
        worker.start()
        break
    if queue:
        return
    canvas._llm_serial_wait_queues.pop(serial_key, None)
