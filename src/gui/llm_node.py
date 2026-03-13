"""LLMNode and WorkflowNode base — draggable nodes on the workflow canvas."""

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
from PySide6.QtWidgets import QGraphicsItem

from .llm_widget import NODE_WIDTH

if TYPE_CHECKING:
    from .connection_item import ConnectionItem

# Shared status colors
STATUS_COLORS = {
    "idle":    QColor("#555555"),
    "running": QColor("#3a8ef5"),
    "looping": QColor("#d18a2f"),
    "done":    QColor("#3aaa5a"),
    "error":   QColor("#e05252"),
}
INVALID_BORDER_COLOR = QColor("#e05252")

PORT_RADIUS = 7
CORNER_RADIUS = 12
INPUT_PORT_EDGE_COLOR = QColor("#6bc6ff")
INPUT_PORT_FILL_COLOR = QColor("#133241")
INPUT_PORT_LABEL_COLOR = QColor("#8ddcff")
OUTPUT_PORT_EDGE_COLOR = QColor("#ffb96f")
OUTPUT_PORT_FILL_COLOR = QColor("#3b2714")
OUTPUT_PORT_LABEL_COLOR = QColor("#ffd7ab")

# LLM node header
_HEADER_COLOR = QColor("#1a3a5c")
_HEADER_TEXT_COLOR = QColor("#8bbfff")
_HEADER_HEIGHT = 28

# Compact node height (header + title row + padding)
_COMPACT_NODE_HEIGHT = 64


# ---------------------------------------------------------------------------
# Glow animation singleton - drives animated border effects for active nodes.
# ---------------------------------------------------------------------------

class _GlowAnimator:
    """Singleton timer that advances a shared glow phase for active workflow nodes."""

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


_ANIMATED_STATUSES = {"running", "looping"}


def glow_phase() -> float:
    """Current normalized glow phase in [0, 1)."""
    return _GlowAnimator.get().phase


def set_node_status(node: "WorkflowNode", status: str) -> None:
    """Apply node status and keep shared glow animation registration in sync."""
    was_animated = node.status in _ANIMATED_STATUSES
    node.status = status
    is_animated = status in _ANIMATED_STATUSES
    animator = _GlowAnimator.get()
    if is_animated and not was_animated:
        animator.register(node)
    elif not is_animated and was_animated:
        animator.unregister(node)
    node.update()


# ---------------------------------------------------------------------------
# WorkflowNode — shared base for LLMNode and FileOpNode
# ---------------------------------------------------------------------------

class WorkflowNode(QGraphicsItem):
    """Base class for all movable workflow nodes.

    Owns: node_id, label_index, status, output_text, connection bookkeeping,
    port proximity tests, itemChange, boundingRect (standard port-padded rect),
    and the shared port-direction-arrow painter helper.

    Subclasses must implement: paint(), set_status(), append_output(),
    clear_output(), output_port_scene_pos(), input_port_scene_pos().
    """

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__()
        self.node_id: str = node_id or str(uuid.uuid4())
        self.label_index: int = label_index
        self.status: str = "idle"
        self.is_invalid: bool = False
        self.output_text: str = ""
        self._connections: List["ConnectionItem"] = []
        self._height: int = 0   # subclasses set this before first paint

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    # ------------------------------------------------------------------
    # Connection bookkeeping
    # ------------------------------------------------------------------

    def add_connection(self, conn: "ConnectionItem") -> None:
        self._connections.append(conn)
        self.update()

    def remove_connection(self, conn: "ConnectionItem") -> None:
        if conn in self._connections:
            self._connections.remove(conn)
            self.update()

    def connections(self) -> List["ConnectionItem"]:
        return list(self._connections)

    def _update_connections(self) -> None:
        for conn in self._connections:
            conn.update_path()

    def _update_scene_connection_routes(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        from .connection_item import ConnectionItem
        for item in scene.items():
            if isinstance(item, ConnectionItem) and item not in self._connections:
                item.update_path()

    def _has_input_connection(self) -> bool:
        return any(conn.target_node is self for conn in self._connections)

    def _has_output_connection(self) -> bool:
        return any(conn.source_node is self for conn in self._connections)

    # ------------------------------------------------------------------
    # Port proximity tests (delegates to subclass port positions)
    # ------------------------------------------------------------------

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        return (scene_pos - self.output_port_scene_pos()).manhattanLength() < PORT_RADIUS * 3

    def is_near_input_port(self, scene_pos: QPointF) -> bool:
        return (scene_pos - self.input_port_scene_pos()).manhattanLength() < PORT_RADIUS * 3

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

    # ------------------------------------------------------------------
    # Shared paint helper
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_port_direction_arrow(
        painter: QPainter,
        start_x: float,
        tip_x: float,
        y: float,
        color: QColor,
    ) -> None:
        arrow_pen = QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(arrow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(start_x, y), QPointF(tip_x, y))
        painter.drawLine(QPointF(tip_x - 5.0, y - 3.7), QPointF(tip_x, y))
        painter.drawLine(QPointF(tip_x - 5.0, y + 3.7), QPointF(tip_x, y))

    @staticmethod
    def _draw_selection_glow(
        painter: QPainter,
        rect: QRectF,
        corner_radius: float,
        active: bool = False,
        active_color: Optional[QColor] = None,
    ) -> None:
        glow_path = QPainterPath()
        glow_path.addRoundedRect(rect, corner_radius, corner_radius)

        if active:
            phase = _GlowAnimator.get().phase
            pulse = 0.55 + 0.45 * math.sin(phase * 2 * math.pi)
            c = active_color or QColor("#8ddcff")
            outer_alpha = int(60 + 70 * pulse)
            inner_alpha = int(170 + 60 * pulse)
            outer_glow_pen = QPen(QColor(c.red(), c.green(), c.blue(), outer_alpha), 8)
            inner_glow_pen = QPen(QColor(c.red(), c.green(), c.blue(), inner_alpha), 3.2)
        else:
            outer_glow_pen = QPen(QColor(122, 215, 255, 90), 8)
            inner_glow_pen = QPen(QColor(160, 230, 255, 220), 3)

        outer_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        inner_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(outer_glow_pen)
        painter.drawPath(glow_path)
        painter.setPen(inner_glow_pen)
        painter.drawPath(glow_path)

    def set_invalid(self, invalid: bool) -> None:
        invalid = bool(invalid)
        if self.is_invalid == invalid:
            return
        self.is_invalid = invalid
        self.update()

    def border_color(self) -> QColor:
        if self.is_invalid and self.status not in _ANIMATED_STATUSES:
            return INVALID_BORDER_COLOR
        return STATUS_COLORS.get(self.status, STATUS_COLORS["idle"])


# ---------------------------------------------------------------------------
# LLMNode
# ---------------------------------------------------------------------------

class LLMNode(WorkflowNode):
    """A draggable workflow LLM-call node. Compact painted node; editing via properties panel."""

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)

        self._title: str = f"LLM {label_index}"
        self._model_id: Optional[str] = None
        self._prompt_text: str = ""
        self._height = _COMPACT_NODE_HEIGHT

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str):
        self._title = value
        self.update()

    @property
    def model_id(self) -> Optional[str]:
        return self._model_id

    @model_id.setter
    def model_id(self, value: str):
        self._model_id = value
        self.update()

    @property
    def prompt_text(self) -> str:
        return self._prompt_text

    @prompt_text.setter
    def prompt_text(self, value: str):
        self._prompt_text = value

    # ------------------------------------------------------------------
    # Status / output
    # ------------------------------------------------------------------

    def set_status(self, status: str) -> None:
        set_node_status(self, status)

    def append_output(self, line: str) -> None:
        self.output_text += line + "\n"

    def clear_output(self) -> None:
        self.output_text = ""

    # ------------------------------------------------------------------
    # Port positions
    # ------------------------------------------------------------------

    def output_port_scene_pos(self, port: str = "output") -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH, self._height / 2))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath) -> None:
        phase = glow_phase()
        cx = NODE_WIDTH / 2
        cy = self._height / 2

        pulse = 0.55 + 0.45 * math.sin(phase * 2 * math.pi)
        halo_rect = QRectF(-5, -5, NODE_WIDTH + 10, self._height + 10)
        halo_path = QPainterPath()
        halo_path.addRoundedRect(halo_rect, CORNER_RADIUS + 5, CORNER_RADIUS + 5)
        halo_pen = QPen(QColor(58, 142, 245, int(60 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)

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

        base_pen = QPen(QColor(58, 142, 245, 140), 1.2)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(base_pen)
        painter.drawPath(border_path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, self._height), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, QBrush(QColor("#252525")))

        # Header strip
        painter.save()
        painter.setClipRect(QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT))
        header_path = QPainterPath()
        header_path.addRoundedRect(
            QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT), CORNER_RADIUS, CORNER_RADIUS
        )
        painter.fillPath(header_path, QBrush(_HEADER_COLOR))
        painter.restore()

        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(_HEADER_TEXT_COLOR)
        painter.drawText(
            QRectF(8, 0, NODE_WIDTH - 16, _HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "LLM CALL",
        )

        # Title in body below header
        title_font = QFont("Segoe UI", 10)
        painter.setFont(title_font)
        painter.setPen(QColor("#c0c0c0"))
        painter.drawText(
            QRectF(12, _HEADER_HEIGHT + 2, NODE_WIDTH - 24, self._height - _HEADER_HEIGHT - 4),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._title,
        )

        is_active = self.status in _ANIMATED_STATUSES
        if self.isSelected():
            self._draw_selection_glow(
                painter,
                QRectF(-2.5, -2.5, NODE_WIDTH + 5.0, self._height + 5.0),
                CORNER_RADIUS + 2.5,
                active=is_active,
                active_color=STATUS_COLORS.get(self.status, QColor("#8ddcff")),
            )

        if self.status == "running":
            self._paint_running_glow(painter, path)
        else:
            border_pen = QPen(self.border_color(), 2)
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
            "id": self.node_id,
            "label_index": self.label_index,
            "x": pos.x(),
            "y": pos.y(),
            "name": self._title,
            "model": self._model_id or "",
            "prompt": self._prompt_text,
        }

    def from_dict(self, data: dict) -> None:
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", f"LLM {self.label_index}")
        if data.get("model"):
            self._model_id = data["model"]
        self._prompt_text = data.get("prompt", "")


# ---------------------------------------------------------------------------
# Start node
# ---------------------------------------------------------------------------

START_NODE_WIDTH = 140
START_NODE_HEIGHT = 80


class StartNode(QGraphicsItem):
    """Permanent pure-trigger root node. Has no model/prompt; fires children immediately."""

    is_start = True
    node_id = "start"

    def __init__(self):
        super().__init__()
        self._connections: List["ConnectionItem"] = []
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    def output_port_scene_pos(self, port: str = "output") -> QPointF:
        return self.mapToScene(QPointF(START_NODE_WIDTH, START_NODE_HEIGHT / 2))

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        port = self.output_port_scene_pos()
        return (scene_pos - port).manhattanLength() < PORT_RADIUS * 3

    def add_connection(self, conn: "ConnectionItem") -> None:
        self._connections.append(conn)
        self.update()

    def remove_connection(self, conn: "ConnectionItem") -> None:
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

    def paint(self, painter: QPainter, option, widget=None) -> None:
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

        if not any(conn.source_node is self for conn in self._connections):
            WorkflowNode._draw_port_direction_arrow(
                painter,
                start_x=START_NODE_WIDTH - 6.0,
                tip_x=START_NODE_WIDTH + 6.0,
                y=cy,
                color=OUTPUT_PORT_LABEL_COLOR,
            )
