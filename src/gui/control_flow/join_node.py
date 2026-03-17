"""JoinNode - waits for N arrivals before continuing downstream once."""

import math as _math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)

from src.gui.llm_node import (
    CORNER_RADIUS,
    INPUT_PORT_EDGE_COLOR,
    INPUT_PORT_FILL_COLOR,
    INPUT_PORT_LABEL_COLOR,
    OUTPUT_PORT_EDGE_COLOR,
    OUTPUT_PORT_FILL_COLOR,
    OUTPUT_PORT_LABEL_COLOR,
    PORT_RADIUS,
    STATUS_COLORS,
    WorkflowNode,
    glow_phase,
    set_node_status,
)
from src.gui.llm_widget import NODE_WIDTH

_HEADER_COLOR = QColor("#21524b")
_HEADER_TEXT_COLOR = QColor("#9cf2d9")
_HEADER_HEIGHT = 28
_JOIN_NODE_HEIGHT = 64


class JoinNode(WorkflowNode):
    """A barrier node that releases once a configured number of arrivals reach it."""

    node_type = "join"

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)
        self._title: str = f"Join {label_index}"
        self.wait_for_count: int = 2
        self._height = _JOIN_NODE_HEIGHT

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str):
        self._title = value
        self.update()

    @property
    def model_id(self) -> Optional[str]:
        return None

    @property
    def prompt_text(self) -> str:
        return ""

    def set_status(self, status: str) -> None:
        set_node_status(self, status)

    def append_output(self, line: str) -> None:
        self.output_text += line + "\n"

    def clear_output(self) -> None:
        self.output_text = ""

    def output_port_scene_pos(self, port: str = "output") -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH, self._height / 2))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath) -> None:
        phase = glow_phase()
        cx = NODE_WIDTH / 2
        cy = self._height / 2
        pulse = 0.55 + 0.45 * _math.sin(phase * 2 * _math.pi)
        halo_rect = QRectF(-5, -5, NODE_WIDTH + 10, self._height + 10)
        halo_path = QPainterPath()
        halo_path.addRoundedRect(halo_rect, CORNER_RADIUS + 5, CORNER_RADIUS + 5)
        halo_pen = QPen(QColor(63, 187, 152, int(70 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)
        angle_deg = phase * 360.0
        grad = QConicalGradient(cx, cy, angle_deg)
        grad.setColorAt(0.00, QColor(156, 242, 217, 240))
        grad.setColorAt(0.25, QColor(25, 80, 67, 60))
        grad.setColorAt(1.00, QColor(156, 242, 217, 240))
        sweep_pen = QPen(QBrush(grad), 3)
        sweep_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(sweep_pen)
        painter.drawPath(border_path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, self._height), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, QBrush(QColor("#252525")))

        painter.save()
        painter.setClipRect(QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT))
        header_path = QPainterPath()
        header_path.addRoundedRect(
            QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT), CORNER_RADIUS, CORNER_RADIUS
        )
        painter.fillPath(header_path, QBrush(_HEADER_COLOR))
        painter.restore()

        header_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(header_font)
        painter.setPen(_HEADER_TEXT_COLOR)
        painter.drawText(
            QRectF(8, 0, NODE_WIDTH - 16, _HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"JOIN  x{self.wait_for_count}",
        )

        title_font = QFont("Segoe UI", 10)
        painter.setFont(title_font)
        painter.setPen(QColor("#c0c0c0"))
        painter.drawText(
            QRectF(12, _HEADER_HEIGHT + 2, NODE_WIDTH - 24, self._height - _HEADER_HEIGHT - 4),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._title,
        )

        if self.isSelected():
            self._draw_selection_glow(
                painter,
                QRectF(-2.5, -2.5, NODE_WIDTH + 5.0, self._height + 5.0),
                CORNER_RADIUS + 2.5,
                active=self.status in {"running", "looping"},
                active_color=STATUS_COLORS.get(self.status, QColor("#9cf2d9")),
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
                painter,
                start_x=-6.0,
                tip_x=6.0,
                y=port_center_y,
                color=INPUT_PORT_LABEL_COLOR,
            )
        if not self._has_output_connection():
            self._draw_port_direction_arrow(
                painter,
                start_x=NODE_WIDTH - 6.0,
                tip_x=NODE_WIDTH + 6.0,
                y=port_center_y,
                color=OUTPUT_PORT_LABEL_COLOR,
            )

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "node_type": self.node_type,
            "id": self.node_id,
            "label_index": self.label_index,
            "x": pos.x(),
            "y": pos.y(),
            "name": self._title,
            "wait_for_count": self.wait_for_count,
        }

    def from_dict(self, data: dict) -> None:
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        raw_count = data.get("wait_for_count", 2)
        if isinstance(raw_count, (int, float)) and not isinstance(raw_count, bool):
            self.wait_for_count = min(9999, max(1, int(raw_count)))
        else:
            self.wait_for_count = 2


def JoinNodeFactory(node_id=None, label_index=1):
    return JoinNode(node_id=node_id, label_index=label_index)

