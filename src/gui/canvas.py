"""WorkflowCanvas — QGraphicsView with node graph interaction."""

import json
import re
from collections import deque
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QPointF, Signal, QObject
from PySide6.QtGui import QColor, QPainter, QWheelEvent, QKeyEvent
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsLineItem,
    QMessageBox,
)

from src.llm.base_provider import LLMProviderRegistry
from src.workers.llm_worker import LLMWorker
from .bubble_node import BubbleNode
from .connection_item import ConnectionItem
from .connection_dialog import ConnectionDialog


class _ExecutionSignals(QObject):
    status_update = Signal(str)
    run_finished = Signal()


class WorkflowCanvas(QGraphicsView):
    status_update = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
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
        self._active_worker: Optional[LLMWorker] = None
        self._exec_signals = _ExecutionSignals()
        self._exec_signals.status_update.connect(self.status_update)

        # Pan state
        self._panning = False
        self._pan_start = QPointF()

    # ------------------------------------------------------------------
    # Background grid
    # ------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect):
        super().drawBackground(painter, rect)
        painter.setPen(QColor("#2a2a2a"))
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

    # ------------------------------------------------------------------
    # Bubble management
    # ------------------------------------------------------------------

    def add_bubble(self) -> BubbleNode:
        self._bubble_counter += 1
        node = BubbleNode(label_index=self._bubble_counter)
        # Place at center of current view
        center = self.mapToScene(self.viewport().rect().center())
        node.setPos(center.x() - 210, center.y() - 150)
        self._scene.addItem(node)
        self._bubbles[node.bubble_id] = node
        return node

    def remove_bubble(self, node: BubbleNode):
        for conn in list(node.connections()):
            self._remove_connection(conn)
        self._scene.removeItem(node)
        self._bubbles.pop(node.bubble_id, None)

    def _remove_connection(self, conn: ConnectionItem):
        conn.detach()
        self._scene.removeItem(conn)
        if conn in self._connections:
            self._connections.remove(conn)

    # ------------------------------------------------------------------
    # Mouse events — connection drawing + pan
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking near an output port
            for node in self._bubbles.values():
                if node.is_near_output_port(scene_pos):
                    self._start_connection(node, scene_pos)
                    return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

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
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if self._drawing_connection and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self._finish_connection(scene_pos)
            return

        super().mouseReleaseEvent(event)

    def _start_connection(self, source: BubbleNode, scene_pos: QPointF):
        self._drawing_connection = True
        self._conn_source = source
        port = source.output_port_scene_pos()
        self._rubber_line = QGraphicsLineItem(port.x(), port.y(), scene_pos.x(), scene_pos.y())
        from PySide6.QtGui import QPen
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

        # Show dialog
        dlg = ConnectionDialog(
            self._conn_source.title, target_node.title, parent=self
        )
        if dlg.exec() == ConnectionDialog.DialogCode.Accepted:
            conn = ConnectionItem(self._conn_source, target_node, dlg.inject_output)
            self._scene.addItem(conn)
            self._connections.append(conn)

        self._conn_source = None

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete:
            for item in self._scene.selectedItems():
                if isinstance(item, ConnectionItem):
                    self._remove_connection(item)
                elif isinstance(item, BubbleNode):
                    self.remove_bubble(item)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_all(self):
        self._run_workflow(list(self._bubbles.values()))

    def run_from_selected(self):
        selected = [i for i in self._scene.selectedItems() if isinstance(i, BubbleNode)]
        if not selected:
            QMessageBox.information(self, "No Selection", "Select a bubble node first.")
            return
        start = selected[0]
        reachable = self._reachable_from(start)
        self._run_workflow(reachable)

    def stop_all(self):
        if self._active_worker:
            self._active_worker.cancel()
        self._running = False

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

    def _topological_sort(self, nodes: List[BubbleNode]) -> Optional[List[BubbleNode]]:
        node_ids = {n.bubble_id for n in nodes}
        in_degree: Dict[str, int] = {n.bubble_id: 0 for n in nodes}
        adj: Dict[str, List[BubbleNode]] = {n.bubble_id: [] for n in nodes}

        for conn in self._connections:
            s_id = conn.source_bubble.bubble_id
            t_id = conn.target_bubble.bubble_id
            if s_id in node_ids and t_id in node_ids:
                adj[s_id].append(conn.target_bubble)
                in_degree[t_id] += 1

        queue = deque([n for n in nodes if in_degree[n.bubble_id] == 0])
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in adj[node.bubble_id]:
                in_degree[nxt.bubble_id] -= 1
                if in_degree[nxt.bubble_id] == 0:
                    queue.append(nxt)

        if len(order) != len(nodes):
            return None  # cycle detected
        return order

    def _run_workflow(self, nodes: List[BubbleNode]):
        if self._running:
            return
        order = self._topological_sort(nodes)
        if order is None:
            QMessageBox.critical(self, "Cycle Detected",
                                 "The workflow contains a cycle. Please remove circular connections.")
            return

        # Reset status
        for node in order:
            node.set_status("idle")
            node.clear_output()

        self._running = True
        self._run_next(order, 0)

    def _run_next(self, order: List[BubbleNode], index: int):
        if index >= len(order) or not self._running:
            self._running = False
            self.status_update.emit("Done.")
            return

        node = order[index]
        node.set_status("running")
        total = len(order)
        self.status_update.emit(f"Running bubble {index + 1} of {total}: {node.title}…")

        # Resolve prompt template
        resolved_prompt = self._resolve_prompt(node)

        model_id = node.model_id
        if not model_id:
            node.append_output("[Error] No model selected.")
            node.set_status("error")
            self._run_next(order, index + 1)
            return

        provider = self._get_provider_for_model(model_id)
        if provider is None:
            node.append_output(f"[Error] Unknown model: {model_id}")
            node.set_status("error")
            self._run_next(order, index + 1)
            return

        worker = LLMWorker(provider, resolved_prompt, model=model_id)
        self._active_worker = worker

        def on_output(line: str):
            node.append_output(line)

        def on_finished(full_output: str):
            node.output_text = full_output
            node.set_status("done")
            self._run_next(order, index + 1)

        def on_error(msg: str):
            node.append_output(f"[Error] {msg}")
            node.set_status("error")
            self._run_next(order, index + 1)

        worker.output_line.connect(on_output)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _resolve_prompt(self, node: BubbleNode) -> str:
        prompt = node.prompt_text

        # Collect all upstream outputs available to this node
        upstream_outputs: Dict[str, str] = {}
        for conn in self._connections:
            if conn.target_bubble is node:
                src = conn.source_bubble
                upstream_outputs[src.bubble_id] = src.output_text
                upstream_outputs[str(src.label_index)] = src.output_text
                # Normalised title key (lowercase, spaces→underscore)
                title_key = re.sub(r"\s+", "_", src.title.lower())
                upstream_outputs[title_key] = src.output_text
                upstream_outputs[f"bubble_{src.label_index}"] = src.output_text

                # Inject via {{prev_output}} or auto-append if flag set
                if conn.inject_output:
                    if "{{prev_output}}" in prompt:
                        prompt = prompt.replace("{{prev_output}}", src.output_text)
                    elif not re.search(r"\{\{[^}]+\}\}", prompt):
                        # No placeholder at all → append
                        if src.output_text.strip():
                            prompt = prompt.rstrip() + "\n\n" + src.output_text

        # Replace remaining {{...}} placeholders
        def replace_var(match):
            key = match.group(1).strip()
            return upstream_outputs.get(key, match.group(0))

        prompt = re.sub(r"\{\{([^}]+)\}\}", replace_var, prompt)
        return prompt

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
        for conn in list(self._connections):
            conn.detach()
        self._scene.clear()
        self._bubbles.clear()
        self._connections.clear()
        self._bubble_counter = 0

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def get_workflow_data(self) -> dict:
        return {
            "bubbles": [n.to_dict() for n in self._bubbles.values()],
            "connections": [c.to_dict() for c in self._connections],
            "bubble_counter": self._bubble_counter,
        }

    def load_workflow_data(self, data: dict):
        self.clear_canvas()
        self._bubble_counter = data.get("bubble_counter", 0)
        for b_data in data.get("bubbles", []):
            idx = b_data.get("label_index", 1)
            node = BubbleNode(bubble_id=b_data.get("id"), label_index=idx)
            node.from_dict(b_data)
            self._scene.addItem(node)
            self._bubbles[node.bubble_id] = node

        for c_data in data.get("connections", []):
            src = self._bubbles.get(c_data["from"])
            tgt = self._bubbles.get(c_data["to"])
            if src and tgt:
                conn = ConnectionItem(src, tgt, c_data.get("inject_output", False))
                self._scene.addItem(conn)
                self._connections.append(conn)
