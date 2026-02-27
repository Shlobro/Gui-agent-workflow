"""WorkflowCanvas — QGraphicsView with node graph interaction."""

from collections import deque
from typing import Dict, List, Optional
from uuid import uuid4

from PySide6.QtCore import Qt, QPointF, Signal, QObject, QRectF
from PySide6.QtGui import QColor, QPainter, QWheelEvent, QKeyEvent, QPen, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsView, QGraphicsScene, QGraphicsLineItem,
    QGraphicsProxyWidget,
    QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QTextEdit,
)

from src.llm.base_provider import LLMProviderRegistry
from src.workers.llm_worker import LLMWorker
from .bubble_node import BubbleNode, StartNode
from .connection_item import ConnectionItem
from .undo_commands import (
    AddBubbleCommand, RemoveBubbleCommand,
    AddConnectionCommand, RemoveConnectionCommand,
    MoveBubbleCommand, TitleChangeCommand, ModelChangeCommand, PasteCommand,
)


class _ExecutionSignals(QObject):
    status_update = Signal(str)
    run_finished = Signal()


class WorkflowCanvas(QGraphicsView):
    status_update = Signal(str)
    selection_changed = Signal()
    run_state_changed = Signal(bool)   # emitted with True when run starts, False when it ends

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._base_scene_rect = QRectF(-5000, -5000, 10000, 10000)
        self._scene.setSceneRect(self._base_scene_rect)
        self.setScene(self._scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#1a1a1a"))

        self._bubbles: Dict[str, BubbleNode] = {}          # id -> node
        self._connections: List[ConnectionItem] = []
        self._bubble_counter = 0

        # Connection-drawing state
        self._drawing_connection = False
        self._conn_source: Optional[BubbleNode] = None
        self._rubber_line: Optional[QGraphicsLineItem] = None

        # Execution state
        self._running = False
        self._no_fanout: bool = False
        self._active_workers: Dict[int, Optional[LLMWorker]] = {}
        self._current_run_exec_ids: set = set()   # exec_ids belonging to the active run only
        self._exec_counter: int = 0
        self._run_id: int = 0
        self._exec_signals = _ExecutionSignals()
        self._exec_signals.status_update.connect(self.status_update)

        # Clipboard (in-memory; persists only for the session)
        self._clipboard: List[dict] = []
        self._clipboard_conns: List[dict] = []
        self._paste_count: int = 0  # resets on each new copy; drives cumulative offset

        # Project working directory (set externally; passed to LLMWorker)
        self._working_directory: Optional[str] = None

        # Pan state
        self._panning = False
        self._pan_start = QPointF()
        self._pan_button: Optional[Qt.MouseButton] = None

        # Undo/redo
        self._undo_stack = QUndoStack(self)
        self._undo_stack.setUndoLimit(100)
        self._undo_in_progress: bool = False
        self._drag_start_positions: Dict[str, QPointF] = {}
        self._title_committed: Dict[str, str] = {}

        # Keep scene bounds large enough to pan back to moved nodes.
        self._scene.changed.connect(self._expand_scene_rect_to_fit_items)
        self._scene.selectionChanged.connect(self.selection_changed)

        # Permanent start node — created after scene is ready
        self._start_node: StartNode = self._add_start_node()

    # ------------------------------------------------------------------
    # Background grid
    # ------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect):
        super().drawBackground(painter, rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        dot_pen = QPen(QColor("#4a4a4a"))
        dot_pen.setCosmetic(True)
        dot_pen.setWidth(1)
        painter.setPen(dot_pen)

        grid = 30
        left = int(rect.left()) - (int(rect.left()) % grid)
        top = int(rect.top()) - (int(rect.top()) % grid)
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(x, y)
                y += grid
            x += grid

        painter.restore()

    def _expand_scene_rect_to_fit_items(self, _changed_rects=None):
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isNull():
            required_rect = self._base_scene_rect
        else:
            padding = 800
            required_rect = items_rect.adjusted(-padding, -padding, padding, padding)
            required_rect = required_rect.united(self._base_scene_rect)

        current_rect = self._scene.sceneRect()
        if not current_rect.contains(required_rect):
            self._scene.setSceneRect(current_rect.united(required_rect))

    # ------------------------------------------------------------------
    # Start node
    # ------------------------------------------------------------------

    def _add_start_node(self) -> StartNode:
        node = StartNode()
        node.setPos(-300, -40)
        self._scene.addItem(node)
        return node

    # ------------------------------------------------------------------
    # Undo/redo raw operations (no stack push — used by commands only)
    # ------------------------------------------------------------------

    def _undo_add_bubble(self, snapshot: dict, label_index: int) -> Optional[BubbleNode]:
        """Reconstruct a node from snapshot and add it to the scene."""
        bubble_id = snapshot.get("id")
        if bubble_id and bubble_id in self._bubbles:
            return self._bubbles[bubble_id]  # already present (safety guard)

        node = BubbleNode(bubble_id=bubble_id, label_index=label_index)
        node.from_dict(snapshot)
        # from_dict may overwrite bubble_id/label_index via data fields; restore
        if bubble_id:
            node.bubble_id = bubble_id
        node.label_index = label_index
        self._scene.addItem(node)
        self._bubbles[node.bubble_id] = node
        self._connect_node_signals(node)
        return node

    def _undo_remove_bubble(self, bubble_id: str):
        """Remove a node (and all its connections) from the scene."""
        node = self._bubbles.get(bubble_id)
        if node is None:
            return
        for conn in list(node.connections()):
            self._undo_remove_connection_item(conn)
        self._scene.removeItem(node)
        self._bubbles.pop(bubble_id, None)
        self._title_committed.pop(bubble_id, None)

    def _undo_add_connection(self, src: BubbleNode, tgt: BubbleNode) -> ConnectionItem:
        """Create a ConnectionItem and register it."""
        conn = ConnectionItem(src, tgt)
        self._scene.addItem(conn)
        conn.update_path()
        self._connections.append(conn)
        return conn

    def _undo_remove_connection_item(self, conn: ConnectionItem):
        """Detach and remove a ConnectionItem."""
        conn.detach()
        self._scene.removeItem(conn)
        if conn in self._connections:
            self._connections.remove(conn)

    def _find_connection(self, src_id: str, tgt_id: str) -> Optional[ConnectionItem]:
        """Find a ConnectionItem by endpoint IDs."""
        for conn in self._connections:
            s = conn.source_bubble.bubble_id
            t = conn.target_bubble.bubble_id
            if s == src_id and t == tgt_id:
                return conn
        return None

    def _connect_node_signals(self, node: BubbleNode):
        """Wire title/model signals for a node so changes push undo commands."""
        bubble_id = node.bubble_id
        self._title_committed[bubble_id] = node.title
        title_edit = node._widget.title_edit
        title_edit.editingFinished.connect(
            lambda _bid=bubble_id, _te=title_edit: self._on_title_editing_finished(_bid, _te)
        )
        node._widget.model_selector.model_changed.connect(
            lambda old, new, _bid=bubble_id: self._on_model_changed(_bid, old, new)
        )

    # ------------------------------------------------------------------
    # Bubble management
    # ------------------------------------------------------------------

    def set_working_directory(self, path: str) -> None:
        """Set the project folder used as cwd for all LLM subprocess calls."""
        self._working_directory = path

    def add_bubble(self) -> BubbleNode:
        self._bubble_counter += 1
        label_index = self._bubble_counter
        center = self.mapToScene(self.viewport().rect().center())
        # Build a snapshot that describes the node-to-be
        snapshot = {
            "id": str(uuid4()),
            "label_index": label_index,
            "x": center.x() - 210,
            "y": center.y() - 150,
            "name": f"Bubble {label_index}",
            "model": "",
            "prompt": "",
        }
        cmd = AddBubbleCommand(self, snapshot, label_index)
        self._undo_stack.push(cmd)
        return self._bubbles[snapshot["id"]]

    def remove_bubble(self, node: BubbleNode):
        if getattr(node, 'bubble_id', None) == "start":
            return
        cmd = RemoveBubbleCommand(self, node)
        self._undo_stack.push(cmd)

    def _remove_connection(self, conn: ConnectionItem):
        src_id = conn.source_bubble.bubble_id
        tgt_id = conn.target_bubble.bubble_id
        cmd = RemoveConnectionCommand(self, src_id, tgt_id)
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Mouse events — connection drawing + pan
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.MouseButton.LeftButton:
            # Check start node output port first, then regular bubbles
            if self._start_node.is_near_output_port(scene_pos):
                self._start_connection(self._start_node, scene_pos)
                return
            for node in self._bubbles.values():
                if node.is_near_output_port(scene_pos):
                    self._start_connection(node, scene_pos)
                    return

        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._panning = True
            self._pan_start = event.pos()
            self._pan_button = event.button()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

        # Capture drag baselines after super() so Qt has updated selection.
        # Also include the item under the cursor in case it wasn't yet selected
        # (click-on-unselected-node-then-drag is the most common move gesture).
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_positions.clear()
            candidates = set(self._scene.selectedItems())
            item_under = self._scene.itemAt(
                self.mapToScene(event.pos()), self.transform()
            )
            if isinstance(item_under, (BubbleNode, StartNode)):
                candidates.add(item_under)
            for item in candidates:
                if isinstance(item, (BubbleNode, StartNode)):
                    bid = item.bubble_id
                    self._drag_start_positions[bid] = QPointF(item.pos())

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        if self._drawing_connection and self._rubber_line:
            scene_pos = self.mapToScene(event.pos())
            line = self._rubber_line.line()
            self._rubber_line.setLine(line.x1(), line.y1(), scene_pos.x(), scene_pos.y())

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == self._pan_button:
            self._panning = False
            self._pan_button = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if self._drawing_connection and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self._finish_connection(scene_pos)
            return

        super().mouseReleaseEvent(event)

        # After super() processes release, check if any tracked node actually moved
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_positions:
            moved = []
            for bid, old_pos in self._drag_start_positions.items():
                if bid == "start":
                    node = self._start_node
                else:
                    node = self._bubbles.get(bid)
                if node and (node.pos() - old_pos).manhattanLength() > 0.5:
                    moved.append((bid, old_pos, node.pos(), bid == "start"))

            if moved:
                if len(moved) > 1:
                    self._undo_stack.beginMacro("Move Nodes")
                for bid, old_pos, new_pos, is_start in moved:
                    self._undo_stack.push(
                        MoveBubbleCommand(self, bid, old_pos, new_pos, is_start)
                    )
                if len(moved) > 1:
                    self._undo_stack.endMacro()

            self._drag_start_positions.clear()

    def _start_connection(self, source: BubbleNode, scene_pos: QPointF):
        self._drawing_connection = True
        self._conn_source = source
        port = source.output_port_scene_pos()
        self._rubber_line = QGraphicsLineItem(port.x(), port.y(), scene_pos.x(), scene_pos.y())
        self._rubber_line.setPen(QPen(QColor("#5599ff"), 2, Qt.PenStyle.DashLine))
        self._scene.addItem(self._rubber_line)

    def _finish_connection(self, scene_pos: QPointF):
        self._drawing_connection = False
        if self._rubber_line:
            self._scene.removeItem(self._rubber_line)
            self._rubber_line = None

        target_node: Optional[BubbleNode] = None
        for node in self._bubbles.values():
            if node is not self._conn_source and node.is_near_input_port(scene_pos):
                target_node = node
                break

        if target_node is None:
            self._conn_source = None
            return

        # Check for duplicate connection
        for conn in self._connections:
            if conn.source_bubble is self._conn_source and conn.target_bubble is target_node:
                self._conn_source = None
                return

        # Capture and clear source before any dialog to prevent re-entrancy.
        source = self._conn_source
        self._conn_source = None

        # Draw-time warnings (cycle takes priority over fan-out).
        src_label = getattr(source, "title", "Start")
        tgt_label = getattr(target_node, "title", "Start")
        if self._would_create_cycle(source, target_node):
            reply = QMessageBox.warning(
                self, "Cycle Warning",
                f'Connecting "{src_label}" \u2192 "{tgt_label}" would create a cycle.\n\n'
                "Nodes in cycles will execute repeatedly until you stop the workflow.\n"
                "Add the connection anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        elif self._source_has_outgoing(source):
            reply = QMessageBox.information(
                self, "Parallel Fan-Out",
                f'"{src_label}" already has an outgoing connection.\n\n'
                f'Adding this one means "{src_label}" will feed multiple nodes, '
                "which will run in parallel when the workflow executes.\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        cmd = AddConnectionCommand(self, source.bubble_id, target_node.bubble_id)
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete:
            deletable = [
                item for item in self._scene.selectedItems()
                if not (getattr(item, 'bubble_id', None) == "start")
                and isinstance(item, (ConnectionItem, BubbleNode))
            ]
            if deletable:
                if len(deletable) > 1:
                    self._undo_stack.beginMacro("Delete")
                for item in deletable:
                    if isinstance(item, ConnectionItem):
                        self._remove_connection(item)
                    elif isinstance(item, BubbleNode):
                        self.remove_bubble(item)
                if len(deletable) > 1:
                    self._undo_stack.endMacro()
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            focused = QApplication.focusWidget()
            text_focused = (
                isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit))
                or isinstance(self._scene.focusItem(), QGraphicsProxyWidget)
            )
            if not text_focused:
                if event.key() == Qt.Key.Key_Z:
                    self._undo_stack.undo()
                    return
                if event.key() == Qt.Key.Key_Y:
                    self._undo_stack.redo()
                    return
                if event.key() == Qt.Key.Key_C:
                    self._copy_selected()
                    return
                if event.key() == Qt.Key.Key_V:
                    self._paste()
                    return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Copy / Paste
    # ------------------------------------------------------------------

    def _copy_selected(self):
        """Snapshot selected BubbleNodes (excluding Start) into the clipboard."""
        selected_nodes = [
            item for item in self._scene.selectedItems()
            if isinstance(item, BubbleNode) and not getattr(item, 'is_start', False)
        ]
        if not selected_nodes:
            return

        selected_ids = {node.bubble_id for node in selected_nodes}
        self._clipboard = [node.to_dict() for node in selected_nodes]
        self._paste_count = 0
        self._clipboard_conns = [
            {"from": conn.source_bubble.bubble_id, "to": conn.target_bubble.bubble_id}
            for conn in self._connections
            if conn.source_bubble.bubble_id in selected_ids
            and conn.target_bubble.bubble_id in selected_ids
        ]

    def _paste(self):
        """Paste clipboard nodes and their internal connections into the canvas."""
        if not self._clipboard:
            return

        self._paste_count += 1
        offset = 40 * self._paste_count

        cmd = PasteCommand(self, self._clipboard, self._clipboard_conns, offset)
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Undo signal handlers
    # ------------------------------------------------------------------

    def _on_title_editing_finished(self, bubble_id: str, title_edit: QLineEdit):
        if self._undo_in_progress:
            return
        new_title = title_edit.text()
        old_title = self._title_committed.get(bubble_id, "")
        if new_title != old_title:
            self._undo_stack.push(TitleChangeCommand(self, bubble_id, old_title, new_title))
            self._title_committed[bubble_id] = new_title

    def _on_model_changed(self, bubble_id: str, old_model_id: str, new_model_id: str):
        if self._undo_in_progress:
            return
        self._undo_stack.push(ModelChangeCommand(self, bubble_id, old_model_id, new_model_id))

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def _visible_model_dropdown(self) -> Optional[QListWidget]:
        for list_widget in self.viewport().findChildren(QListWidget, "model_selector_dropdown"):
            if list_widget.isVisible():
                return list_widget
        return None

    @staticmethod
    def _scroll_dropdown_list(list_widget: QListWidget, delta: int):
        scroll_bar = list_widget.verticalScrollBar()
        if scroll_bar is None:
            return

        single_step = scroll_bar.singleStep() or 20
        wheel_steps = delta / 120.0
        if wheel_steps == 0:
            wheel_steps = delta / 15.0

        scroll_bar.setValue(scroll_bar.value() - int(wheel_steps * single_step))

    def wheelEvent(self, event: QWheelEvent):
        dropdown = self._visible_model_dropdown()
        if dropdown is not None:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta != 0:
                self._scroll_dropdown_list(dropdown, delta)
            event.accept()
            return

        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            event.accept()
            return

        factor = 1.15 if delta > 0 else 1 / 1.15
        current_zoom = self.transform().m11()
        new_zoom = current_zoom * factor
        if 0.2 <= new_zoom <= 4.0:
            self.scale(factor, factor)
        event.accept()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _check_project_folder(self) -> bool:
        """Return True if a project folder is set; otherwise show a warning and return False."""
        if self._working_directory:
            return True
        QMessageBox.warning(
            self, "No Project Folder",
            "Please open a project folder before running a workflow.\n\n"
            "Use File → Open Project Folder… to choose one.",
        )
        return False

    def run_all(self):
        if not self._check_project_folder():
            return
        reachable = self._reachable_from(self._start_node)
        nodes = [n for n in reachable if not getattr(n, 'is_start', False)]
        if not nodes:
            self.status_update.emit("Nothing to run \u2014 connect nodes to Start first.")
            return
        errors = self._validate_nodes(nodes)
        if errors:
            QMessageBox.warning(
                self, "Cannot Run",
                "Fix these issues before running:\n\n" + "\n".join(errors),
            )
            return
        self._run_workflow(nodes, roots=self._direct_children(self._start_node))

    def run_selected_only(self):
        if not self._check_project_folder():
            return
        selected = [
            i for i in self._scene.selectedItems()
            if isinstance(i, BubbleNode) and not getattr(i, 'is_start', False)
        ]
        if not selected:
            QMessageBox.information(self, "No Selection", "Select at least one bubble first.")
            return
        if len(selected) > 1:
            reply = QMessageBox.question(
                self, "Run Multiple",
                f"Run {len(selected)} selected nodes simultaneously (without fan-out)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        errors = self._validate_nodes(selected)
        if errors:
            QMessageBox.warning(
                self, "Cannot Run",
                "Fix these issues before running:\n\n" + "\n".join(errors),
            )
            return
        self._run_workflow(selected, roots=list(selected), no_fanout=True)

    def run_from_here(self):
        if not self._check_project_folder():
            return
        selected = [
            i for i in self._scene.selectedItems()
            if isinstance(i, BubbleNode) and not getattr(i, 'is_start', False)
        ]
        if len(selected) != 1:
            return
        start = selected[0]
        reachable = self._reachable_from(start)
        nodes = [n for n in reachable if not getattr(n, 'is_start', False)]
        errors = self._validate_nodes(nodes)
        if errors:
            QMessageBox.warning(
                self, "Cannot Run",
                "Fix these issues before running:\n\n" + "\n".join(errors),
            )
            return
        self._run_workflow(nodes, roots=[start])

    def stop_all(self):
        self._running = False
        self.run_state_changed.emit(False)
        self._no_fanout = False
        for worker in list(self._active_workers.values()):
            if worker is not None:
                worker.cancel()
        # Reset any nodes still showing "running" so the glow animator stops.
        for node in self._bubbles.values():
            if node.status == "running":
                node.set_status("idle")
        # Do not clear _active_workers here — keep Python refs alive until
        # each thread's finished/error callback fires and removes its entry,
        # preventing QThread destruction while the thread is still running.
        self.status_update.emit("Stopped.")

    def _reachable_from(self, start: BubbleNode) -> List[BubbleNode]:
        visited = []
        queue = deque([start])
        seen = {start.bubble_id}
        while queue:
            node = queue.popleft()
            visited.append(node)
            for conn in node.connections():
                if conn.source_bubble is node:
                    nxt = conn.target_bubble
                    if nxt.bubble_id not in seen:
                        seen.add(nxt.bubble_id)
                        queue.append(nxt)
        return visited

    def _would_create_cycle(self, source: BubbleNode, target: BubbleNode) -> bool:
        """Return True if adding source→target would create a cycle."""
        return source in self._reachable_from(target)

    def _source_has_outgoing(self, source: BubbleNode) -> bool:
        """Return True if source already has at least one outgoing connection."""
        return any(conn.source_bubble is source for conn in self._connections)

    def _validate_nodes(self, nodes: List[BubbleNode]) -> List[str]:
        """Return error strings for nodes missing a prompt or model."""
        errors = []
        for node in nodes:
            title = getattr(node, 'title', node.bubble_id)
            if not node.prompt_text.strip():
                errors.append(f'\u2022 "{title}" has no prompt.')
            if not node.model_id:
                errors.append(f'\u2022 "{title}" has no model selected.')
        return errors

    def _direct_children(self, node) -> List[BubbleNode]:
        """Return immediate downstream neighbours of node."""
        return [
            conn.target_bubble for conn in self._connections
            if conn.source_bubble is node
        ]

    def _run_workflow(self, nodes: List[BubbleNode], roots: List[BubbleNode], no_fanout: bool = False):
        if self._running:
            return
        for node in nodes:
            node.set_status("idle")
            node.clear_output()
        self._running = True
        self.run_state_changed.emit(True)
        self._no_fanout = no_fanout
        self._run_id += 1
        self._current_run_exec_ids.clear()
        n = len(roots)
        self.status_update.emit(f"Running\u2026 ({n} node{'s' if n != 1 else ''} triggered)")
        for node in roots:
            self._trigger_node(node)
        self._check_drain()  # handles zero-roots case

    def _trigger_node(self, node: BubbleNode):
        """Schedule one new invocation of node if execution is active."""
        if not self._running:
            return
        self._exec_counter += 1
        self._fire_invocation(node, self._exec_counter)

    def _fire_invocation(self, node: BubbleNode, exec_id: int):
        """Launch one LLMWorker invocation tagged with exec_id."""
        self._active_workers[exec_id] = None  # reserve slot before any early return
        self._current_run_exec_ids.add(exec_id)
        node.set_status("running")
        model_id = node.model_id
        if not model_id:
            node.append_output("[Error] No model selected.")
            node.set_status("error")
            del self._active_workers[exec_id]
            self._current_run_exec_ids.discard(exec_id)
            return
        provider = self._get_provider_for_model(model_id)
        if provider is None:
            node.append_output(f"[Error] Unknown model: {model_id}")
            node.set_status("error")
            del self._active_workers[exec_id]
            self._current_run_exec_ids.discard(exec_id)
            return

        worker = LLMWorker(provider, node.prompt_text, model=model_id,
                           working_directory=self._working_directory)
        self._active_workers[exec_id] = worker

        run_id = self._run_id

        def on_output(line: str, _n=node, _e=exec_id, _r=run_id):
            if _r == self._run_id and self._running and _e in self._active_workers:
                _n.append_output(line)

        def on_finished(full: str, _n=node, _e=exec_id, _r=run_id):
            self._on_invocation_done(_n, _e, full, error=False, run_id=_r)

        def on_error(msg: str, _n=node, _e=exec_id, _r=run_id):
            self._on_invocation_done(_n, _e, msg, error=True, run_id=_r)

        worker.output_line.connect(on_output)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _on_invocation_done(self, node: BubbleNode, exec_id: int, result: str, error: bool, run_id: int = 0):
        """Main-thread callback when one invocation finishes or errors."""
        if exec_id not in self._active_workers:
            return                          # double-call guard
        del self._active_workers[exec_id]
        self._current_run_exec_ids.discard(exec_id)
        if run_id != self._run_id or not self._running:
            self._check_drain()             # ref released — drain in case new run is now empty
            return                          # stale callback from a previous run

        if error:
            node.append_output(f"[Error] {result}")
            node.set_status("error")
            # Dead end — do not trigger children on error
        else:
            node.output_text = result
            node.set_status("done")
            if not self._no_fanout:
                for conn in self._connections:
                    if conn.source_bubble is node:
                        self._trigger_node(conn.target_bubble)

        self._check_drain()

    def _check_drain(self):
        """Emit Done and clear _running when all current-run workers are gone."""
        if self._running and not self._current_run_exec_ids:
            self._running = False
            self.run_state_changed.emit(False)
            self.status_update.emit("Done.")

    def _get_provider_for_model(self, model_id: str):
        for provider in LLMProviderRegistry.all():
            for mid, _ in provider.get_models():
                if mid == model_id:
                    return provider
        return None

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear_canvas(self):
        self.stop_all()
        for conn in list(self._connections):
            conn.detach()
        self._scene.clear()
        self._scene.setSceneRect(self._base_scene_rect)
        self._bubbles.clear()
        self._connections.clear()
        self._bubble_counter = 0
        self._start_node = self._add_start_node()
        self._undo_stack.clear()
        self._title_committed.clear()

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def get_workflow_data(self) -> dict:
        sp = self._start_node.pos()
        return {
            "bubbles": [n.to_dict() for n in self._bubbles.values()],
            "connections": [c.to_dict() for c in self._connections],
            "bubble_counter": self._bubble_counter,
            "start_pos": [sp.x(), sp.y()],
        }

    def load_workflow_data(self, data: dict):
        self.clear_canvas()
        self._bubble_counter = data.get("bubble_counter", 0)
        sp = data.get("start_pos")
        if sp:
            self._start_node.setPos(sp[0], sp[1])
        for b_data in data.get("bubbles", []):
            idx = b_data.get("label_index", 1)
            node = BubbleNode(bubble_id=b_data.get("id"), label_index=idx)
            node.from_dict(b_data)
            self._scene.addItem(node)
            self._bubbles[node.bubble_id] = node
            self._connect_node_signals(node)

        for c_data in data.get("connections", []):
            if c_data.get("to") == "start":
                continue  # Start has no input port; skip invalid edges
            src = self._start_node if c_data["from"] == "start" else self._bubbles.get(c_data["from"])
            tgt = self._bubbles.get(c_data["to"])
            if src and tgt:
                conn = ConnectionItem(src, tgt)
                self._scene.addItem(conn)
                self._connections.append(conn)
        self._expand_scene_rect_to_fit_items()
        self._undo_stack.clear()
