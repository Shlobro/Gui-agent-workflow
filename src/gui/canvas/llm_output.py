"""Shared LLM output helpers for WorkflowCanvas execution."""

from __future__ import annotations

from src.gui.llm_node import LLMNode, WorkflowNode
from src.gui.llm_sessions.session_state import normalize_session_name


def llm_shared_session_name(node: LLMNode) -> str:
    if node.resume_named_session_name.strip():
        return normalize_session_name(node.resume_named_session_name)
    if node.save_session_enabled and node.save_session_name.strip():
        return normalize_session_name(node.save_session_name)
    return ""


def iter_output_targets(canvas, node: WorkflowNode) -> list[WorkflowNode]:
    if not isinstance(node, LLMNode):
        return [node]
    session_name = llm_shared_session_name(node)
    if not session_name:
        return [node]
    targets: list[WorkflowNode] = []
    seen: set[str] = set()
    for candidate in canvas._nodes.values():
        if (
            isinstance(candidate, LLMNode)
            and llm_shared_session_name(candidate) == session_name
            and candidate.node_id not in seen
        ):
            targets.append(candidate)
            seen.add(candidate.node_id)
    if node.node_id not in seen:
        targets.append(node)
    return targets


def append_output_line(canvas, node: WorkflowNode, line: str) -> None:
    for target in iter_output_targets(canvas, node):
        target.append_output(line)
        if canvas.on_output_line:
            canvas.on_output_line(target, line)


def clear_node_output(canvas, node: WorkflowNode) -> None:
    for target in iter_output_targets(canvas, node):
        target.clear_output()
        if canvas.on_output_cleared:
            canvas.on_output_cleared(target)


def llm_prompt_metadata_lines(node: LLMNode, composed_prompt: str) -> list[str]:
    lines = [
        f"[Node] {node.title}",
        f"[Session ID] {node.resume_named_session_name or node.save_session_name or '(node-local)'}",
        "[Prompt]",
    ]
    prompt_lines = composed_prompt.splitlines() or [""]
    lines.extend(prompt_lines)
    lines.append("[Response]")
    return lines


def start_llm_output_block(canvas, node: LLMNode, composed_prompt: str) -> None:
    call_index = canvas._llm_invocation_counts.get(node.node_id, 0) + 1
    canvas._llm_invocation_counts[node.node_id] = call_index
    if node.output_text.strip():
        append_output_line(canvas, node, "")
    append_output_line(canvas, node, f"=== Call {call_index} ===")
    for line in llm_prompt_metadata_lines(node, composed_prompt):
        append_output_line(canvas, node, line)
