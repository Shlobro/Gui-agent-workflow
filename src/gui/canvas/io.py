"""_IOMixin — graph mutation helpers, save/load, clipboard for WorkflowCanvas."""

from typing import TYPE_CHECKING, Optional

from src.gui.connection_item import ConnectionItem
from src.gui.file_op_node import NODE_TYPE_MAP
from src.gui.llm_node import LLMNode, StartNode, WorkflowNode
from src.gui.undo_commands import PasteCommand
from src.gui.workflow_io import parse_workflow_data, build_workflow_data, get_provider_for_model
from src.gui.variables import VariableNode

if TYPE_CHECKING:
    from src.gui.canvas import WorkflowCanvas

GraphNode = WorkflowNode


class _IOMixin:
    """Graph mutation, undo helpers, clipboard, and save/load methods mixed into WorkflowCanvas."""

    # ------------------------------------------------------------------
    # Undo/redo primitive helpers (called directly by QUndoCommand subclasses)
    # ------------------------------------------------------------------

    def _undo_add_node(self: "WorkflowCanvas", snapshot: dict, label_index: int):
        node_id = snapshot.get("id")
        if node_id and node_id in self._nodes:
            return self._nodes[node_id]

        node_type = snapshot.get("node_type", "llm")
        if node_type in NODE_TYPE_MAP:
            node = NODE_TYPE_MAP[node_type](node_id=node_id, label_index=label_index)
            node.from_dict(snapshot)
            if node_id:
                node.node_id = node_id
            node.label_index = label_index
        else:
            node = LLMNode(node_id=node_id, label_index=label_index)
            node.from_dict(snapshot)
            if node_id:
                node.node_id = node_id
            node.label_index = label_index
        if isinstance(node, LLMNode):
            provider = get_provider_for_model(node.model_id or "")
            if provider is None or not provider.supports_session_resume(node.model_id):
                node.resume_session_enabled = False
                node.save_session_enabled = False
                node.save_session_name = ""
                node.resume_named_session_name = ""
                node.saved_session_id = ""
                node.saved_session_provider = ""

        self._scene.addItem(node)
        self._nodes[node.node_id] = node
        self._title_committed[node.node_id] = node.title
        self.refresh_node_validation_state()
        return node

    def _undo_remove_node(self: "WorkflowCanvas", node_id: str):
        node = self._nodes.get(node_id)
        if node is None:
            return
        self._clear_join_state_for_node(node_id)
        for exec_id, nid in list(self._exec_node.items()):
            if nid == node_id:
                worker = self._active_workers.get(exec_id)
                if worker is not None:
                    worker.cancel()
                self._exec_node.pop(exec_id, None)
                self._retired_exec_ids.add(exec_id)
        serial_keys_to_remove = {f"node:{node_id}"}
        for session_name, record in self._named_sessions.items():
            if record.get("owner_node_id") == node_id:
                serial_keys_to_remove.add(f"named:{session_name}")
        for serial_key in serial_keys_to_remove:
            for _queued_key, exec_id, _worker, _run_id, _lt, _lp, _jt in self._llm_serial_wait_queues.get(serial_key, []):
                self._active_workers.pop(exec_id, None)
                self._exec_node.pop(exec_id, None)
                self._exec_lineage.pop(exec_id, None)
                self._exec_streamed_output.pop(exec_id, None)
                self._current_run_exec_ids.discard(exec_id)
                self._llm_serial_waiting_exec_ids.discard(exec_id)
            self._llm_serial_wait_queues.pop(serial_key, None)
            self._llm_serial_resume_nodes.discard(serial_key)
        if node.status == "running":
            node.set_status("idle")
        for conn in list(node.connections()):
            self._undo_remove_connection_item(conn)
        self._scene.removeItem(node)
        self._nodes.pop(node_id, None)
        self._title_committed.pop(node_id, None)
        for session_name, record in list(self._named_sessions.items()):
            if record.get("owner_node_id") == node_id:
                self._named_sessions.pop(session_name, None)
        self.reconcile_named_sessions()
        self.refresh_node_validation_state()

    def _undo_add_connection(
        self: "WorkflowCanvas",
        src,
        tgt: GraphNode,
        source_port: str = "output",
        vertices: Optional[list[tuple[float, float]]] = None,
        reconcile: bool = True,
    ) -> ConnectionItem:
        conn = ConnectionItem(src, tgt, source_port=source_port)
        if vertices:
            conn.set_manual_points_from_tuples(vertices)
        self._scene.addItem(conn)
        self._connections.append(conn)
        if reconcile:
            self.reconcile_named_sessions()
            if any(isinstance(node, LLMNode) for node in self.selected_workflow_nodes()):
                self.selection_changed.emit()
        return conn

    def _undo_remove_connection_item(
        self: "WorkflowCanvas", conn: ConnectionItem, reconcile: bool = True
    ):
        conn.detach()
        self._scene.removeItem(conn)
        if conn in self._connections:
            self._connections.remove(conn)
        if reconcile:
            self.reconcile_named_sessions()
            if any(isinstance(node, LLMNode) for node in self.selected_workflow_nodes()):
                self.selection_changed.emit()

    def _find_connection(self: "WorkflowCanvas", src_id: str, tgt_id: str,
                         source_port: str = "output") -> Optional[ConnectionItem]:
        for conn in self._connections:
            if (conn.source_node.node_id == src_id
                    and conn.target_node.node_id == tgt_id
                    and getattr(conn, "source_port", "output") == source_port):
                return conn
        return None

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _copy_selected(self: "WorkflowCanvas"):
        selected_nodes = [
            item for item in self._scene.selectedItems()
            if isinstance(item, WorkflowNode) and not isinstance(item, StartNode)
        ]
        if not selected_nodes:
            return
        selected_ids = {node.node_id for node in selected_nodes}
        self._clipboard = [node.to_dict() for node in selected_nodes]
        self._paste_count = 0
        self._clipboard_conns = [
            conn.to_dict()
            for conn in self._connections
            if conn.source_node.node_id in selected_ids
            and conn.target_node.node_id in selected_ids
        ]

    def _paste(self: "WorkflowCanvas"):
        if not self._clipboard:
            return
        self._paste_count += 1
        offset = 40 * self._paste_count
        cmd = PasteCommand(self, self._clipboard, self._clipboard_conns, offset)
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Canvas reset
    # ------------------------------------------------------------------

    def clear_canvas(self: "WorkflowCanvas"):
        self.stop_all()
        for conn in list(self._connections):
            conn.detach()
        self._scene.clear()
        self._scene.setSceneRect(self._base_scene_rect)
        self._nodes.clear()
        self._connections.clear()
        self._node_counter = 0
        self._start_node = self._add_start_node()
        self.refresh_node_validation_state()
        self._undo_stack.clear()
        self._title_committed.clear()
        self._llm_serial_resume_nodes.clear()
        self._llm_serial_waiting_exec_ids.clear()
        self._llm_serial_wait_queues.clear()
        self._named_sessions.clear()
        self._clear_variable_runtime_state()

    # ------------------------------------------------------------------
    # Workflow save / load
    # ------------------------------------------------------------------

    def get_workflow_data(self: "WorkflowCanvas") -> dict:
        return build_workflow_data(
            self._nodes.values(),
            self._connections,
            self._node_counter,
            self._start_node,
            self._named_sessions,
        )

    def load_workflow_data(self: "WorkflowCanvas", data: dict):
        parsed = parse_workflow_data(data)
        self.clear_canvas()
        self._node_counter = parsed["node_counter"]
        self._named_sessions = parsed["named_sessions"]

        sp = parsed["start_pos"]
        if sp is not None:
            self._start_node.setPos(sp[0], sp[1])

        for b_data in parsed["nodes"]:
            idx = b_data.get("label_index", 1)
            node_type = b_data.get("node_type", "llm")
            if node_type in NODE_TYPE_MAP:
                node = NODE_TYPE_MAP[node_type](node_id=b_data.get("id"), label_index=idx)
                node.from_dict(b_data)
            else:
                node = LLMNode(node_id=b_data.get("id"), label_index=idx)
                node.from_dict(b_data)
            if isinstance(node, LLMNode):
                provider = get_provider_for_model(node.model_id or "")
                if provider is None or not provider.supports_session_resume(node.model_id):
                    node.resume_session_enabled = False
                    node.save_session_enabled = False
                    node.save_session_name = ""
                    node.resume_named_session_name = ""
                    node.saved_session_id = ""
                    node.saved_session_provider = ""
            self._scene.addItem(node)
            self._nodes[node.node_id] = node
            self._title_committed[node.node_id] = node.title

        for c_data in parsed["connections"]:
            src_id = c_data.get("from")
            tgt_id = c_data.get("to")
            source_port = c_data.get("source_port", "output")
            vertices = c_data.get("vertices", [])
            src = self._start_node if src_id == "start" else self._nodes.get(src_id)
            tgt = self._nodes.get(tgt_id)
            if src and tgt:
                self._undo_add_connection(
                    src,
                    tgt,
                    source_port=source_port,
                    vertices=vertices,
                    reconcile=False,
                )

        self.reconcile_named_sessions()
        self.refresh_node_validation_state()
        self._expand_scene_rect_to_fit_items()
        self._undo_stack.clear()
