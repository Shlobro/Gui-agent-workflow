"""Overview helpers for the main window side panel."""

from __future__ import annotations

from src.gui.conditional_node import ConditionalNode
from src.gui.connection_item import ConnectionItem
from src.gui.control_flow.join_node import JoinNode
from src.gui.file_op_node import AttentionNode, FileOpNode
from src.gui.git_action_node import GitActionNode
from src.gui.llm_node import LLMNode
from src.gui.loop_node import LoopNode
from src.gui.script_runner.script_node import ScriptNode
from src.gui.variables import VariableNode


def selected_nodes(main_window) -> list:
    return main_window.canvas.selected_workflow_nodes()


def selected_connections(main_window) -> list[ConnectionItem]:
    return main_window.canvas.selected_connection_items()


def connection_endpoint_name(node) -> str:
    if getattr(node, "is_start", False):
        return "Start"
    return getattr(node, "title", getattr(node, "node_id", "(unknown)"))


def set_connection_overview(main_window, conn: ConnectionItem) -> None:
    source_name = connection_endpoint_name(conn.source_node)
    target_name = connection_endpoint_name(conn.target_node)
    source_id = getattr(conn.source_node, "node_id", "(unknown)")
    target_id = getattr(conn.target_node, "node_id", "(unknown)")
    source_port = getattr(conn, "source_port", "output")
    vertex_count = len(conn.editable_points())
    lines = [
        "Selected Arrow",
        "",
        "Endpoints",
        f"- From: {source_name}",
        f"- To: {target_name}",
        "",
        "Connection Details",
        f"- Source node id: {source_id}",
        f"- Target node id: {target_id}",
        f"- Source port: {source_port}",
        f"- Bend points: {vertex_count}",
        "",
        "Editing",
        "- Double-click line segment: add bend point",
        "- Drag bend handle: move bend point",
        "- Shift+click bend handle: remove bend point",
        "- Delete: delete selected arrow",
        "- Ctrl+Z / Ctrl+Y: undo / redo",
    ]
    main_window._panel.set_overview_text("\n".join(lines))


def refresh_panel_overview(main_window) -> None:
    if not hasattr(main_window, "_panel"):
        return
    selected_node_items = selected_nodes(main_window)
    selected_connection_items = selected_connections(main_window)
    if len(selected_connection_items) == 1 and not selected_node_items:
        set_connection_overview(main_window, selected_connection_items[0])
        return

    nodes = main_window.canvas.workflow_nodes()
    main_window.canvas.refresh_node_validation_state()

    llm_count = 0
    file_op_count = 0
    conditional_count = 0
    loop_count = 0
    join_count = 0
    attention_count = 0
    git_action_count = 0
    script_count = 0
    variable_count = 0
    resumable_llm_count = 0
    saved_llm_session_count = 0
    saved_named_session_count = 0
    invalid_nodes: list[str] = []

    for node in nodes:
        if getattr(node, "is_invalid", False):
            invalid_nodes.append(getattr(node, "title", node.node_id))
        if isinstance(node, AttentionNode):
            attention_count += 1
        elif isinstance(node, ConditionalNode):
            conditional_count += 1
        elif isinstance(node, LoopNode):
            loop_count += 1
        elif isinstance(node, JoinNode):
            join_count += 1
        elif isinstance(node, GitActionNode):
            git_action_count += 1
        elif isinstance(node, ScriptNode):
            script_count += 1
        elif isinstance(node, VariableNode):
            variable_count += 1
        elif isinstance(node, FileOpNode):
            file_op_count += 1
        elif isinstance(node, LLMNode):
            llm_count += 1
            if node.resume_session_enabled:
                resumable_llm_count += 1
            if node.saved_session_id.strip():
                saved_llm_session_count += 1

    saved_named_session_count = main_window.canvas.named_session_count(saved_only=True)

    options = main_window._effective_preview_prompt_injection_options()
    prepend_template_contents, append_template_contents, one_off_text, one_off_placement = (
        main_window._resolve_prompt_injection_payload(options)
    )

    lines = [
        "Workflow Summary",
        f"Working directory: {main_window.canvas._working_directory or '(not selected)'}",
        f"Connections: {main_window.canvas.connection_count()}",
        f"Selected nodes: {len(selected_node_items)}",
        f"Selected arrows: {len(selected_connection_items)}",
        "",
        "Node Counts",
        f"- Total: {len(nodes)}",
        f"- LLM: {llm_count}",
        f"- File Ops: {file_op_count}",
        f"- Conditional: {conditional_count}",
        f"- Attention: {attention_count}",
        f"- Loop: {loop_count}",
        f"- Join: {join_count}",
        f"- Git Action: {git_action_count}",
        f"- Script: {script_count}",
        f"- Variable: {variable_count}",
        f"- LLM Resume Enabled: {resumable_llm_count}",
        f"- Saved LLM Sessions: {saved_llm_session_count}",
        f"- Saved Named Sessions: {saved_named_session_count}",
        "",
        f"Invalid Nodes: {len(invalid_nodes)}",
    ]
    if invalid_nodes:
        for title in invalid_nodes[:10]:
            lines.append(f"- {title}")
        if len(invalid_nodes) > 10:
            lines.append(f"- ... and {len(invalid_nodes) - 10} more")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "Prompt Injection (applies to every LLM prompt)",
            f"- Enabled templates: {len(options.enabled_template_ids)}",
            f"- One-off placement: {one_off_placement}",
            "",
            f"Prepend blocks: {len(prepend_template_contents)}",
        ]
    )
    if prepend_template_contents:
        for idx, section in enumerate(prepend_template_contents, start=1):
            lines.append(f"[prepend #{idx}]")
            lines.append(section)
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    lines.append(f"Append blocks: {len(append_template_contents)}")
    if append_template_contents:
        for idx, section in enumerate(append_template_contents, start=1):
            lines.append(f"[append #{idx}]")
            lines.append(section)
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    lines.append("One-off block:")
    lines.append(one_off_text.strip() if one_off_text.strip() else "(none)")
    main_window._panel.set_overview_text("\n".join(lines))
