"""QUndoCommand subclasses for graph-level undo/redo."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional
from uuid import uuid4

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

from .file_op_node import NODE_TYPE_DISPLAY_NAMES

if TYPE_CHECKING:
    from .canvas import WorkflowCanvas
    from .llm_node import LLMNode, StartNode
    from .file_op_node import FileOpNode

# Command IDs for merge support
_MOVE_CMD_ID = 1001


def _command_node_label(snapshot: dict) -> str:
    """Return a human-readable node label for undo/redo command text."""
    node_type = snapshot.get("node_type", "llm")
    if node_type == "llm":
        base = "LLM Node"
    else:
        base = NODE_TYPE_DISPLAY_NAMES.get(str(node_type), str(node_type).replace("_", " ").title()) + " Node"
    return base


class AddNodeCommand(QUndoCommand):
    """Push when a new workflow node is created."""

    def __init__(self, canvas: "WorkflowCanvas", snapshot: dict, label_index: int):
        super().__init__(f"Add {_command_node_label(snapshot)}")
        self._canvas = canvas
        self._snapshot = snapshot
        self._label_index = label_index

    def redo(self):
        self._canvas._undo_add_node(self._snapshot, self._label_index)

    def undo(self):
        self._canvas._undo_remove_node(self._snapshot["id"])


class RemoveNodeCommand(QUndoCommand):
    """Push when a workflow node is about to be deleted."""

    def __init__(self, canvas: "WorkflowCanvas", node: "LLMNode | FileOpNode"):
        self._canvas = canvas
        self._snapshot = node.to_dict()
        super().__init__(f"Delete {_command_node_label(self._snapshot)}")
        self._label_index = node.label_index
        # Capture connected edges before node is removed
        self._conn_snapshots: List[dict] = [
            conn.to_dict() for conn in node.connections()
        ]

    def redo(self):
        self._canvas._undo_remove_node(self._snapshot["id"])

    def undo(self):
        node = self._canvas._undo_add_node(self._snapshot, self._label_index)
        if node is None:
            return
        for c in self._conn_snapshots:
            src_id, tgt_id = c.get("from"), c.get("to")
            if src_id == "start":
                src = self._canvas._start_node
            else:
                src = self._canvas._nodes.get(src_id)
            if tgt_id == "start":
                tgt = self._canvas._start_node
            else:
                tgt = self._canvas._nodes.get(tgt_id)
            if src and tgt:
                self._canvas._undo_add_connection(src, tgt)


class AddConnectionCommand(QUndoCommand):
    """Push when a ConnectionItem is created."""

    def __init__(self, canvas: "WorkflowCanvas", src_id: str, tgt_id: str):
        super().__init__("Add Connection")
        self._canvas = canvas
        self._src_id = src_id
        self._tgt_id = tgt_id

    def _resolve(self):
        src = (self._canvas._start_node if self._src_id == "start"
               else self._canvas._nodes.get(self._src_id))
        tgt = (self._canvas._start_node if self._tgt_id == "start"
               else self._canvas._nodes.get(self._tgt_id))
        return src, tgt

    def redo(self):
        src, tgt = self._resolve()
        if src and tgt:
            self._canvas._undo_add_connection(src, tgt)

    def undo(self):
        conn = self._canvas._find_connection(self._src_id, self._tgt_id)
        if conn:
            self._canvas._undo_remove_connection_item(conn)


class RemoveConnectionCommand(QUndoCommand):
    """Push when a ConnectionItem is deleted."""

    def __init__(self, canvas: "WorkflowCanvas", src_id: str, tgt_id: str):
        super().__init__("Delete Connection")
        self._canvas = canvas
        self._src_id = src_id
        self._tgt_id = tgt_id

    def _resolve(self):
        src = (self._canvas._start_node if self._src_id == "start"
               else self._canvas._nodes.get(self._src_id))
        tgt = (self._canvas._start_node if self._tgt_id == "start"
               else self._canvas._nodes.get(self._tgt_id))
        return src, tgt

    def redo(self):
        conn = self._canvas._find_connection(self._src_id, self._tgt_id)
        if conn:
            self._canvas._undo_remove_connection_item(conn)

    def undo(self):
        src, tgt = self._resolve()
        if src and tgt:
            self._canvas._undo_add_connection(src, tgt)


class MoveNodeCommand(QUndoCommand):
    """Push after a node drag completes. Consecutive moves of the same node merge."""

    def __init__(self, canvas: "WorkflowCanvas", node_id: str,
                 old_pos: QPointF, new_pos: QPointF, is_start: bool = False):
        super().__init__("Move Node")
        self._canvas = canvas
        self._node_id = node_id
        self._old_pos = QPointF(old_pos)
        self._new_pos = QPointF(new_pos)
        self._is_start = is_start

    def id(self) -> int:  # noqa: A003
        return _MOVE_CMD_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, MoveNodeCommand):
            return False
        if other._node_id != self._node_id:
            return False
        self._new_pos = QPointF(other._new_pos)
        return True

    def _node(self) -> Optional["StartNode | LLMNode | FileOpNode"]:
        if self._is_start:
            return self._canvas._start_node
        return self._canvas._nodes.get(self._node_id)

    def redo(self):
        node = self._node()
        if node:
            node.setPos(self._new_pos)

    def undo(self):
        node = self._node()
        if node:
            node.setPos(self._old_pos)


class TitleChangeCommand(QUndoCommand):
    """Push when the title QLineEdit commits a new value."""

    def __init__(self, canvas: "WorkflowCanvas", node_id: str,
                 old_title: str, new_title: str):
        node = canvas._nodes.get(node_id)
        snapshot = node.to_dict() if node is not None else {"node_type": "llm"}
        super().__init__(f"Rename {_command_node_label(snapshot)}")
        self._canvas = canvas
        self._node_id = node_id
        self._old_title = old_title
        self._new_title = new_title

    def _node(self) -> Optional["LLMNode | FileOpNode"]:
        return self._canvas._nodes.get(self._node_id)

    def redo(self):
        node = self._node()
        if node:
            self._canvas._undo_in_progress = True
            try:
                node.title = self._new_title
                self._canvas._title_committed[self._node_id] = self._new_title
            finally:
                self._canvas._undo_in_progress = False
            self._canvas.notify_node_changed(self._node_id)

    def undo(self):
        node = self._node()
        if node:
            self._canvas._undo_in_progress = True
            try:
                node.title = self._old_title
                self._canvas._title_committed[self._node_id] = self._old_title
            finally:
                self._canvas._undo_in_progress = False
            self._canvas.notify_node_changed(self._node_id)


class ModelChangeCommand(QUndoCommand):
    """Push when the user selects a different model."""

    def __init__(self, canvas: "WorkflowCanvas", node_id: str,
                 old_model_id: str, new_model_id: str):
        super().__init__("Change Model")
        self._canvas = canvas
        self._node_id = node_id
        self._old_model_id = old_model_id
        self._new_model_id = new_model_id

    def _node(self) -> Optional["LLMNode"]:
        from .llm_node import LLMNode
        node = self._canvas._nodes.get(self._node_id)
        return node if isinstance(node, LLMNode) else None

    def redo(self):
        node = self._node()
        if node:
            self._canvas._undo_in_progress = True
            try:
                node.model_id = self._new_model_id
            finally:
                self._canvas._undo_in_progress = False
            self._canvas.notify_node_changed(self._node_id)

    def undo(self):
        node = self._node()
        if node:
            self._canvas._undo_in_progress = True
            try:
                node.model_id = self._old_model_id
            finally:
                self._canvas._undo_in_progress = False
            self._canvas.notify_node_changed(self._node_id)


class PasteCommand(QUndoCommand):
    """Push when clipboard nodes are pasted."""

    def __init__(self, canvas: "WorkflowCanvas", clipboard: List[dict],
                 clipboard_conns: List[dict], offset: float):
        super().__init__("Paste")
        self._canvas = canvas
        self._clipboard_conns = clipboard_conns
        self._offset = offset

        # Pre-generate new IDs and snapshots with adjusted positions
        self._id_map: Dict[str, str] = {}
        self._node_snapshots: List[dict] = []
        self._label_indices: List[int] = []

        for data in clipboard:
            canvas._node_counter += 1
            new_id = str(uuid4())
            self._id_map[data["id"]] = new_id
            snap = dict(data)
            snap["id"] = new_id
            snap["x"] = data.get("x", 0) + offset
            snap["y"] = data.get("y", 0) + offset
            snap["label_index"] = canvas._node_counter
            self._node_snapshots.append(snap)
            self._label_indices.append(canvas._node_counter)

    def redo(self):
        new_nodes = []
        for snap, li in zip(self._node_snapshots, self._label_indices):
            node = self._canvas._undo_add_node(snap, li)
            if node:
                new_nodes.append(node)

        # Recreate internal connections
        for conn_data in self._clipboard_conns:
            src_id = self._id_map.get(conn_data["from"])
            tgt_id = self._id_map.get(conn_data["to"])
            if src_id and tgt_id:
                src = self._canvas._nodes.get(src_id)
                tgt = self._canvas._nodes.get(tgt_id)
                if src and tgt:
                    self._canvas._undo_add_connection(src, tgt)

        # Select pasted nodes, deselect others
        self._canvas._scene.clearSelection()
        for node in new_nodes:
            node.setSelected(True)

    def undo(self):
        for snap in self._node_snapshots:
            self._canvas._undo_remove_node(snap["id"])
