"""_IOMixin — graph mutation helpers, save/load, clipboard for WorkflowCanvas."""

from typing import TYPE_CHECKING, Optional

from src.gui.connection_item import ConnectionItem
from src.gui.file_op_node import NODE_TYPE_MAP
from src.gui.llm_node import LLMNode, StartNode, WorkflowNode
from src.gui.undo_commands import PasteCommand
from src.gui.workflow_io import parse_workflow_data, build_workflow_data

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

        self._scene.addItem(node)
        self._nodes[node.node_id] = node
        self._title_committed[node.node_id] = node.title
        return node

    def _undo_remove_node(self: "WorkflowCanvas", node_id: str):
        node = self._nodes.get(node_id)
        if node is None:
            return
        for exec_id, nid in list(self._exec_node.items()):
            if nid == node_id:
                worker = self._active_workers.get(exec_id)
                if worker is not None:
                    worker.cancel()
                self._exec_node.pop(exec_id, None)
                self._retired_exec_ids.add(exec_id)
        if node.status == "running":
            node.set_status("idle")
        for conn in list(node.connections()):
            self._undo_remove_connection_item(conn)
        self._scene.removeItem(node)
        self._nodes.pop(node_id, None)
        self._title_committed.pop(node_id, None)

    def _undo_add_connection(self: "WorkflowCanvas", src, tgt: GraphNode) -> ConnectionItem:
        conn = ConnectionItem(src, tgt)
        self._scene.addItem(conn)
        conn.update_path()
        self._connections.append(conn)
        return conn

    def _undo_remove_connection_item(self: "WorkflowCanvas", conn: ConnectionItem):
        conn.detach()
        self._scene.removeItem(conn)
        if conn in self._connections:
            self._connections.remove(conn)

    def _find_connection(self: "WorkflowCanvas", src_id: str, tgt_id: str) -> Optional[ConnectionItem]:
        for conn in self._connections:
            if conn.source_node.node_id == src_id and conn.target_node.node_id == tgt_id:
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
            {"from": conn.source_node.node_id, "to": conn.target_node.node_id}
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
        self._undo_stack.clear()
        self._title_committed.clear()

    # ------------------------------------------------------------------
    # Workflow save / load
    # ------------------------------------------------------------------

    def get_workflow_data(self: "WorkflowCanvas") -> dict:
        return build_workflow_data(
            self._nodes.values(), self._connections, self._node_counter, self._start_node
        )

    def load_workflow_data(self: "WorkflowCanvas", data: dict):
        parsed = parse_workflow_data(data)
        self.clear_canvas()
        self._node_counter = parsed["node_counter"]

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
            self._scene.addItem(node)
            self._nodes[node.node_id] = node
            self._title_committed[node.node_id] = node.title

        for c_data in parsed["connections"]:
            src_id = c_data.get("from")
            tgt_id = c_data.get("to")
            src = self._start_node if src_id == "start" else self._nodes.get(src_id)
            tgt = self._nodes.get(tgt_id)
            if src and tgt:
                conn = ConnectionItem(src, tgt)
                self._scene.addItem(conn)
                self._connections.append(conn)

        self._expand_scene_rect_to_fit_items()
        self._undo_stack.clear()
