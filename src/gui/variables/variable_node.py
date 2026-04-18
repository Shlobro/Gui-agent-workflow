"""Variable workflow node for downstream prompt substitution."""

from __future__ import annotations

import keyword
import math as _math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFont, QPainter, QPainterPath, QPen

from src.gui.llm_node import (
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

VARIABLE_TYPE_TEXT = "text"
VARIABLE_TYPE_NUMBER = "number"
VARIABLE_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    (VARIABLE_TYPE_TEXT, "Text"),
    (VARIABLE_TYPE_NUMBER, "Number"),
)

_TYPE_LABELS = dict(VARIABLE_TYPE_OPTIONS)
_HEADER_COLOR = QColor("#4f4a8a")
_HEADER_TEXT_COLOR = QColor("#e6e0ff")
_CORNER_RADIUS = 12
_HEADER_HEIGHT = 28
_NODE_HEIGHT = 64


def is_valid_variable_name(name: str) -> bool:
    normalized = (name or "").strip()
    return bool(normalized) and normalized.isidentifier() and not keyword.iskeyword(normalized)


def is_valid_number_value(value: str) -> bool:
    try:
        float((value or "").strip())
    except (TypeError, ValueError):
        return False
    return True


class VariableNode(WorkflowNode):
    node_type = "variable"

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)
        self._title = f"Variable {label_index}"
        self.variable_name = ""
        self.variable_type = VARIABLE_TYPE_TEXT
        self.variable_value = ""
        self._height = _NODE_HEIGHT

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
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
        pulse = 0.55 + 0.45 * _math.sin(phase * 2 * _math.pi)
        halo_rect = QRectF(-5, -5, NODE_WIDTH + 10, self._height + 10)
        halo_path = QPainterPath()
        halo_path.addRoundedRect(halo_rect, _CORNER_RADIUS + 5, _CORNER_RADIUS + 5)
        halo_pen = QPen(QColor(58, 142, 245, int(60 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)
        grad = QConicalGradient(NODE_WIDTH / 2, self._height / 2, phase * 360.0)
        grad.setColorAt(0.00, QColor(120, 200, 255, 240))
        grad.setColorAt(0.25, QColor(30, 80, 160, 60))
        grad.setColorAt(1.00, QColor(120, 200, 255, 240))
        sweep_pen = QPen(QBrush(grad), 3)
        sweep_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(sweep_pen)
        painter.drawPath(border_path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, self._height), _CORNER_RADIUS, _CORNER_RADIUS)
        painter.fillPath(path, QBrush(QColor("#252525")))

        painter.save()
        painter.setClipRect(QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT))
        header_path = QPainterPath()
        header_path.addRoundedRect(
            QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT), _CORNER_RADIUS, _CORNER_RADIUS
        )
        painter.fillPath(header_path, QBrush(_HEADER_COLOR))
        painter.restore()

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(_HEADER_TEXT_COLOR)
        painter.drawText(
            QRectF(8, 0, NODE_WIDTH - 16, _HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "VARIABLE",
        )

        painter.setFont(QFont("Segoe UI", 10))
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
                _CORNER_RADIUS + 2.5,
                active=self.status in {"running", "looping"},
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
                painter, start_x=-6.0, tip_x=6.0, y=port_center_y, color=INPUT_PORT_LABEL_COLOR
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
            "variable_name": self.variable_name,
            "variable_type": self.variable_type,
            "variable_value": self.variable_value,
        }

    def from_dict(self, data: dict) -> None:
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        self.variable_name = data.get("variable_name", "")
        variable_type = data.get("variable_type", VARIABLE_TYPE_TEXT)
        self.variable_type = (
            variable_type if variable_type in _TYPE_LABELS else VARIABLE_TYPE_TEXT
        )
        self.variable_value = data.get("variable_value", "")


def variable_type_label(variable_type: str) -> str:
    return _TYPE_LABELS.get(variable_type, "Text")
