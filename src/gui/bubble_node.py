"""BubbleNode — a draggable node on the workflow canvas."""

import math
import uuid
import weakref
from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt, QPointF, QTimer
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QFont,
    QConicalGradient,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsProxyWidget,
)

from .bubble_widget import BubbleWidget, NODE_WIDTH

if TYPE_CHECKING:
    from .connection_item import ConnectionItem

# Status colors
STATUS_COLORS = {
    "idle":    QColor("#555555"),
    "running": QColor("#3a8ef5"),
    "done":    QColor("#3aaa5a"),
    "error":   QColor("#e05252"),
}

NODE_HEIGHT = 300
PORT_RADIUS = 7
CORNER_RADIUS = 12
INPUT_PORT_EDGE_COLOR = QColor("#6bc6ff")
INPUT_PORT_FILL_COLOR = QColor("#133241")
INPUT_PORT_LABEL_COLOR = QColor("#8ddcff")
OUTPUT_PORT_EDGE_COLOR = QColor("#ffb96f")
OUTPUT_PORT_FILL_COLOR = QColor("#3b2714")
OUTPUT_PORT_LABEL_COLOR = QColor("#ffd7ab")

# ---------------------------------------------------------------------------
# Glow animation singleton — drives "running" border animation for all nodes
# ---------------------------------------------------------------------------

class _GlowAnimator:
    """Singleton timer that advances a shared glow phase for running nodes."""

    _instance: Optional["_GlowAnimator"] = None

    def __init__(self):
        self._phase: float = 0.0
        self._nodes: weakref.WeakSet = weakref.WeakSet()
        self._timer = QTimer()
        self._timer.setInterval(30)        # ~33 fps
        self._timer.timeout.connect(self._tick)

    @classmethod
    def get(cls) -> "_GlowAnimator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, node) -> None:
        self._nodes.add(node)
        if not self._timer.isActive():
            self._timer.start()

    def unregister(self, node) -> None:
        self._nodes.discard(node)
        if not self._nodes and self._timer.isActive():
            self._timer.stop()

    @property
    def phase(self) -> float:
        return self._phase

    def _tick(self) -> None:
        if not self._nodes:
            self._timer.stop()
            return
        self._phase = (self._phase + 0.012) % 1.0   # full cycle ≈ 2.5 s
        for node in list(self._nodes):
            node.update()


class BubbleNode(QGraphicsItem):
    """A draggable workflow bubble node."""

    def __init__(self, bubble_id: Optional[str] = None, label_index: int = 1):
        super().__init__()
        self.bubble_id = bubble_id or str(uuid.uuid4())
        self.label_index = label_index
        self.status = "idle"
        self.output_text = ""
        self._connections: List["ConnectionItem"] = []

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

        self._widget = BubbleWidget(on_layout_change=self._update_height)
        self._widget.title_edit.setText(f"Bubble {label_index}")
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(self._widget)
        self._proxy.setPos(0, 0)

        self._widget.adjustSize()
        self._height = max(NODE_HEIGHT, self._widget.sizeHint().height() + 20)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def title(self) -> str:
        return self._widget.title_edit.text()

    @title.setter
    def title(self, value: str):
        self._widget.title_edit.setText(value)

    @property
    def model_id(self) -> Optional[str]:
        return self._widget.get_model_id()

    @model_id.setter
    def model_id(self, value: str):
        self._widget.set_model_id(value)

    @property
    def prompt_text(self) -> str:
        return self._widget.prompt_edit.toPlainText()

    @prompt_text.setter
    def prompt_text(self, value: str):
        self._widget.prompt_edit.setPlainText(value)

    # ------------------------------------------------------------------
    # Status / output
    # ------------------------------------------------------------------

    def set_status(self, status: str):
        was_running = self.status == "running"
        self.status = status
        animator = _GlowAnimator.get()
        if status == "running" and not was_running:
            animator.register(self)
        elif status != "running" and was_running:
            animator.unregister(self)
        self.update()

    def append_output(self, line: str):
        self._widget.show_output(True)
        self._widget.output_edit.appendPlainText(line)
        self.output_text += line + "\n"
        self._update_height()

    def clear_output(self):
        self.output_text = ""
        self._widget.output_edit.clear()
        self._widget.show_output(False)
        self._update_height()

    def _update_height(self):
        new_h = max(NODE_HEIGHT, self._widget.sizeHint().height() + 20)
        if new_h != self._height:
            self.prepareGeometryChange()
            self._height = new_h
            self._update_connections()
            self._update_scene_connection_routes()

    # ------------------------------------------------------------------
    # Port positions
    # ------------------------------------------------------------------

    def output_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH, self._height / 2))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        port = self.output_port_scene_pos()
        return (scene_pos - port).manhattanLength() < PORT_RADIUS * 3

    def is_near_input_port(self, scene_pos: QPointF) -> bool:
        port = self.input_port_scene_pos()
        return (scene_pos - port).manhattanLength() < PORT_RADIUS * 3

    # ------------------------------------------------------------------
    # Connections bookkeeping
    # ------------------------------------------------------------------

    def add_connection(self, conn: "ConnectionItem"):
        self._connections.append(conn)
        self.update()

    def remove_connection(self, conn: "ConnectionItem"):
        if conn in self._connections:
            self._connections.remove(conn)
            self.update()

    def connections(self) -> List["ConnectionItem"]:
        return list(self._connections)

    def _update_connections(self):
        for conn in self._connections:
            conn.update_path()

    def _update_scene_connection_routes(self):
        scene = self.scene()
        if scene is None:
            return

        from .connection_item import ConnectionItem

        for item in scene.items():
            if isinstance(item, ConnectionItem) and item not in self._connections:
                item.update_path()

    def _has_input_connection(self) -> bool:
        return any(conn.target_bubble is self for conn in self._connections)

    def _has_output_connection(self) -> bool:
        return any(conn.source_bubble is self for conn in self._connections)

    @staticmethod
    def _draw_port_direction_arrow(
        painter: QPainter,
        start_x: float,
        tip_x: float,
        y: float,
        color: QColor,
    ):
        arrow_pen = QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(arrow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(start_x, y), QPointF(tip_x, y))
        painter.drawLine(QPointF(tip_x - 5.0, y - 3.7), QPointF(tip_x, y))
        painter.drawLine(QPointF(tip_x - 5.0, y + 3.7), QPointF(tip_x, y))

    # ------------------------------------------------------------------
    # QGraphicsItem overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return QRectF(-PORT_RADIUS, -PORT_RADIUS,
                      NODE_WIDTH + PORT_RADIUS * 2, self._height + PORT_RADIUS * 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._update_connections()
            self._update_scene_connection_routes()
        return super().itemChange(change, value)

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath):
        """Draw an animated sweeping glow around the border when status is 'running'."""
        phase = _GlowAnimator.get().phase
        cx = NODE_WIDTH / 2
        cy = self._height / 2

        # Outer soft halo — pulses in opacity
        pulse = 0.55 + 0.45 * math.sin(phase * 2 * math.pi)
        halo_rect = QRectF(-5, -5, NODE_WIDTH + 10, self._height + 10)
        halo_path = QPainterPath()
        halo_path.addRoundedRect(halo_rect, CORNER_RADIUS + 5, CORNER_RADIUS + 5)
        halo_pen = QPen(QColor(58, 142, 245, int(60 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)

        # Rotating bright spot via conical gradient
        angle_deg = phase * 360.0
        grad = QConicalGradient(cx, cy, angle_deg)
        grad.setColorAt(0.00, QColor(120, 200, 255, 240))
        grad.setColorAt(0.12, QColor(58, 142, 245, 180))
        grad.setColorAt(0.25, QColor(30, 80, 160, 60))
        grad.setColorAt(0.75, QColor(30, 80, 160, 20))
        grad.setColorAt(1.00, QColor(120, 200, 255, 240))

        sweep_pen = QPen(QBrush(grad), 3)
        sweep_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(sweep_pen)
        painter.drawPath(border_path)

        # Thin solid base border so shape stays crisp
        base_pen = QPen(QColor(58, 142, 245, 140), 1.2)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(base_pen)
        painter.drawPath(border_path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, self._height), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, QBrush(QColor("#252525")))

        if self.isSelected():
            glow_rect = QRectF(-2.5, -2.5, NODE_WIDTH + 5.0, self._height + 5.0)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, CORNER_RADIUS + 2.5, CORNER_RADIUS + 2.5)

            outer_glow_pen = QPen(QColor(122, 215, 255, 90), 8)
            outer_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outer_glow_pen)
            painter.drawPath(glow_path)

            inner_glow_pen = QPen(QColor(160, 230, 255, 220), 3)
            inner_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(inner_glow_pen)
            painter.drawPath(glow_path)

        if self.status == "running":
            self._paint_running_glow(painter, path)
        else:
            color = STATUS_COLORS.get(self.status, STATUS_COLORS["idle"])
            border_pen = QPen(color, 2)
            border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(border_pen)
            painter.drawPath(path)

        port_center_y = self._height / 2

        painter.setPen(QPen(OUTPUT_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(OUTPUT_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(NODE_WIDTH, port_center_y), PORT_RADIUS, PORT_RADIUS)

        painter.setPen(QPen(INPUT_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(INPUT_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(0, port_center_y), PORT_RADIUS, PORT_RADIUS)

        if not self._has_input_connection():
            self._draw_port_direction_arrow(
                painter, start_x=-6.0, tip_x=6.0, y=port_center_y,
                color=INPUT_PORT_LABEL_COLOR,
            )

        if not self._has_output_connection():
            self._draw_port_direction_arrow(
                painter, start_x=NODE_WIDTH - 6.0, tip_x=NODE_WIDTH + 6.0,
                y=port_center_y, color=OUTPUT_PORT_LABEL_COLOR,
            )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "id": self.bubble_id,
            "label_index": self.label_index,
            "x": pos.x(),
            "y": pos.y(),
            "name": self.title,
            "model": self.model_id or "",
            "prompt": self.prompt_text,
        }

    def from_dict(self, data: dict):
        self.bubble_id = data.get("id", self.bubble_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self.title = data.get("name", f"Bubble {self.label_index}")
        if data.get("model"):
            self.model_id = data["model"]
        self.prompt_text = data.get("prompt", "")


# ---------------------------------------------------------------------------
# Start node
# ---------------------------------------------------------------------------

START_NODE_WIDTH = 140
START_NODE_HEIGHT = 80


class StartNode(QGraphicsItem):
    """Permanent pure-trigger root node. Has no model/prompt; fires children immediately."""

    is_start = True
    bubble_id = "start"

    def __init__(self):
        super().__init__()
        self._connections: List["ConnectionItem"] = []
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    def output_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(START_NODE_WIDTH, START_NODE_HEIGHT / 2))

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        port = self.output_port_scene_pos()
        return (scene_pos - port).manhattanLength() < PORT_RADIUS * 3

    def add_connection(self, conn: "ConnectionItem"):
        self._connections.append(conn)
        self.update()

    def remove_connection(self, conn: "ConnectionItem"):
        if conn in self._connections:
            self._connections.remove(conn)
            self.update()

    def connections(self) -> List["ConnectionItem"]:
        return list(self._connections)

    def boundingRect(self) -> QRectF:
        return QRectF(
            -PORT_RADIUS, -PORT_RADIUS,
            START_NODE_WIDTH + PORT_RADIUS * 2,
            START_NODE_HEIGHT + PORT_RADIUS * 2,
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for conn in self._connections:
                conn.update_path()
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, START_NODE_WIDTH, START_NODE_HEIGHT), 12, 12)
        painter.fillPath(path, QBrush(QColor("#1a2e1a")))

        if self.isSelected():
            glow_rect = QRectF(-2.5, -2.5, START_NODE_WIDTH + 5.0, START_NODE_HEIGHT + 5.0)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, 14.5, 14.5)

            outer_glow_pen = QPen(QColor(122, 215, 255, 90), 8)
            outer_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outer_glow_pen)
            painter.drawPath(glow_path)

            inner_glow_pen = QPen(QColor(160, 230, 255, 220), 3)
            inner_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(inner_glow_pen)
            painter.drawPath(glow_path)

        border_pen = QPen(QColor("#3aaa5a"), 2)
        border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(border_pen)
        painter.drawPath(path)

        font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#3aaa5a"))
        painter.drawText(
            QRectF(0, 0, START_NODE_WIDTH, START_NODE_HEIGHT),
            Qt.AlignmentFlag.AlignCenter,
            "\u25b6 START",
        )

        cy = START_NODE_HEIGHT / 2
        painter.setPen(QPen(OUTPUT_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(OUTPUT_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(START_NODE_WIDTH, cy), PORT_RADIUS, PORT_RADIUS)

        if not any(conn.source_bubble is self for conn in self._connections):
            BubbleNode._draw_port_direction_arrow(
                painter,
                start_x=START_NODE_WIDTH - 6.0,
                tip_x=START_NODE_WIDTH + 6.0,
                y=cy,
                color=OUTPUT_PORT_LABEL_COLOR,
            )
