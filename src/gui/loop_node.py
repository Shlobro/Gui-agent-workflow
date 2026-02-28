"""LoopNode — fires its loop port N times then fires its done port once."""

import math as _math
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QFont,
    QConicalGradient,
)

from .llm_node import (
    WorkflowNode,
    STATUS_COLORS,
    PORT_RADIUS,
    INPUT_PORT_EDGE_COLOR, INPUT_PORT_FILL_COLOR, INPUT_PORT_LABEL_COLOR,
    CORNER_RADIUS,
)
from .llm_widget import NODE_WIDTH

# Port colors for loop/done output ports
_LOOP_PORT_EDGE_COLOR = QColor("#3a8ef5")
_LOOP_PORT_FILL_COLOR = QColor("#0f1a30")
_DONE_PORT_EDGE_COLOR = QColor("#3aaa5a")
_DONE_PORT_FILL_COLOR = QColor("#0f3020")

# Header colors
_HEADER_COLOR = QColor("#1a3a5a")
_HEADER_TEXT_COLOR = QColor("#60c0ff")
_HEADER_HEIGHT = 28

# Taller than compact LLM nodes to fit two labeled ports
_LOOP_NODE_HEIGHT = 80


# ---------------------------------------------------------------------------
# LoopNode
# ---------------------------------------------------------------------------

class LoopNode(WorkflowNode):
    """A node that fires its loop port N times then fires its done port once."""

    node_type = "loop"  # class-level constant for serialization

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)

        self._title: str = f"Loop {label_index}"
        self.loop_count: int = 3
        self._height = _LOOP_NODE_HEIGHT

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

    # Compatibility shims — LoopNode is not an LLM node
    @property
    def model_id(self) -> Optional[str]:
        return None

    @property
    def prompt_text(self) -> str:
        return ""

    # ------------------------------------------------------------------
    # Status / output
    # ------------------------------------------------------------------

    def set_status(self, status: str) -> None:
        self.status = status
        self.update()

    def append_output(self, line: str) -> None:
        self.output_text += line + "\n"

    def clear_output(self) -> None:
        self.output_text = ""

    # ------------------------------------------------------------------
    # Port positions — two output ports on the right edge
    # ------------------------------------------------------------------

    def output_port_scene_pos(self, port: str = "output") -> QPointF:
        """Return scene position of the named output port.

        port="loop" → upper-right at 33% height
        port="done" → lower-right at 67% height
        port="output" → defaults to loop port position
        """
        if port == "done":
            y = self._height * 0.67
        else:
            y = self._height * 0.33  # loop port (default)
        return self.mapToScene(QPointF(NODE_WIDTH, y))

    def loop_port_scene_pos(self) -> QPointF:
        return self.output_port_scene_pos("loop")

    def done_port_scene_pos(self) -> QPointF:
        return self.output_port_scene_pos("done")

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    # ------------------------------------------------------------------
    # Port proximity helpers — separate methods for each output port
    # ------------------------------------------------------------------

    def is_near_loop_port(self, scene_pos: QPointF) -> bool:
        return (scene_pos - self.loop_port_scene_pos()).manhattanLength() < PORT_RADIUS * 3

    def is_near_done_port(self, scene_pos: QPointF) -> bool:
        return (scene_pos - self.done_port_scene_pos()).manhattanLength() < PORT_RADIUS * 3

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        """Returns True if near either output port (for generic node scanning)."""
        return self.is_near_loop_port(scene_pos) or self.is_near_done_port(scene_pos)

    def _has_loop_connection(self) -> bool:
        return any(
            conn.source_node is self and getattr(conn, "source_port", "output") == "loop"
            for conn in self._connections
        )

    def _has_done_connection(self) -> bool:
        return any(
            conn.source_node is self and getattr(conn, "source_port", "output") == "done"
            for conn in self._connections
        )

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath):
        phase = (id(self) * 0.001) % 1.0
        cx = NODE_WIDTH / 2
        cy = self._height / 2
        pulse = 0.55 + 0.45 * _math.sin(phase * 2 * _math.pi)
        halo_rect = QRectF(-5, -5, NODE_WIDTH + 10, self._height + 10)
        halo_path = QPainterPath()
        halo_path.addRoundedRect(halo_rect, CORNER_RADIUS + 5, CORNER_RADIUS + 5)
        halo_pen = QPen(QColor(58, 142, 245, int(60 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)
        angle_deg = phase * 360.0
        grad = QConicalGradient(cx, cy, angle_deg)
        grad.setColorAt(0.00, QColor(96, 192, 255, 240))
        grad.setColorAt(0.25, QColor(30, 80, 160, 60))
        grad.setColorAt(1.00, QColor(96, 192, 255, 240))
        sweep_pen = QPen(QBrush(grad), 3)
        sweep_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(sweep_pen)
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
            f"LOOP  ×{self.loop_count}",
        )

        # Title in body area
        title_font = QFont("Segoe UI", 10)
        painter.setFont(title_font)
        painter.setPen(QColor("#c0c0c0"))
        body_y = _HEADER_HEIGHT + 2
        body_h = self._height - _HEADER_HEIGHT - 4
        painter.drawText(
            QRectF(12, body_y, NODE_WIDTH - 40, body_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._title,
        )

        if self.isSelected():
            glow_rect = QRectF(-2.5, -2.5, NODE_WIDTH + 5.0, self._height + 5.0)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, CORNER_RADIUS + 2.5, CORNER_RADIUS + 2.5)
            outer_glow_pen = QPen(QColor(58, 142, 245, 90), 8)
            outer_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outer_glow_pen)
            painter.drawPath(glow_path)
            inner_glow_pen = QPen(QColor(96, 192, 255, 220), 3)
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

        # Input port (left center)
        in_y = self._height / 2
        painter.setPen(QPen(INPUT_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(INPUT_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(0, in_y), PORT_RADIUS, PORT_RADIUS)
        if not self._has_input_connection():
            self._draw_port_direction_arrow(
                painter, start_x=-6.0, tip_x=6.0, y=in_y,
                color=INPUT_PORT_LABEL_COLOR,
            )

        # Loop port (upper right, ~33%)
        loop_y = self._height * 0.33
        painter.setPen(QPen(_LOOP_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(_LOOP_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(NODE_WIDTH, loop_y), PORT_RADIUS, PORT_RADIUS)

        # "↺" label next to loop port
        small_font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(small_font)
        painter.setPen(_LOOP_PORT_EDGE_COLOR)
        painter.drawText(
            QRectF(NODE_WIDTH - 22, loop_y - 8, 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            "\u21ba",
        )

        if not self._has_loop_connection():
            self._draw_port_direction_arrow(
                painter,
                start_x=NODE_WIDTH - 6.0,
                tip_x=NODE_WIDTH + 6.0,
                y=loop_y,
                color=_LOOP_PORT_EDGE_COLOR,
            )

        # Done port (lower right, ~67%)
        done_y = self._height * 0.67
        painter.setPen(QPen(_DONE_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(_DONE_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(NODE_WIDTH, done_y), PORT_RADIUS, PORT_RADIUS)

        # "✓" label next to done port
        painter.setPen(_DONE_PORT_EDGE_COLOR)
        painter.drawText(
            QRectF(NODE_WIDTH - 22, done_y - 8, 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            "\u2713",
        )

        if not self._has_done_connection():
            self._draw_port_direction_arrow(
                painter,
                start_x=NODE_WIDTH - 6.0,
                tip_x=NODE_WIDTH + 6.0,
                y=done_y,
                color=_DONE_PORT_EDGE_COLOR,
            )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "node_type": self.node_type,
            "id": self.node_id,
            "label_index": self.label_index,
            "x": pos.x(),
            "y": pos.y(),
            "name": self._title,
            "loop_count": self.loop_count,
        }

    def from_dict(self, data: dict) -> None:
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        raw_count = data.get("loop_count", 3)
        self.loop_count = min(9999, max(1, int(raw_count))) if isinstance(raw_count, (int, float)) and not isinstance(raw_count, bool) else 3


# ---------------------------------------------------------------------------
# Factory function for NODE_TYPE_MAP
# ---------------------------------------------------------------------------

def LoopNodeFactory(node_id=None, label_index=1):
    return LoopNode(node_id=node_id, label_index=label_index)
