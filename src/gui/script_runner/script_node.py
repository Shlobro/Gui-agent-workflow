"""ScriptNode - runs a selected .bat, .cmd, or .ps1 script inside the project folder."""

from __future__ import annotations

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

SCRIPT_NODE_TYPE = "script_runner"
SCRIPT_NODE_DISPLAY_NAME = "Run Script"
SCRIPT_FILE_FILTER = "Script Files (*.bat *.cmd *.ps1)"
ALLOWED_SCRIPT_SUFFIXES = (".bat", ".cmd", ".ps1")

_SCRIPT_ACCENT = QColor("#365f86")
_CORNER_RADIUS = 12
_HEADER_HEIGHT = 28
_SCRIPT_NODE_HEIGHT = 64


class ScriptNode(WorkflowNode):
    """Compact node that executes a script file relative to the selected project folder."""

    node_type = SCRIPT_NODE_TYPE

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)
        self._title = f"{SCRIPT_NODE_DISPLAY_NAME} {label_index}"
        self.script_path: str = ""
        self.auto_send_enter: bool = False
        self._height = _SCRIPT_NODE_HEIGHT

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

    def set_status(self, status: str):
        set_node_status(self, status)

    def append_output(self, line: str):
        self.output_text += line + "\n"

    def clear_output(self):
        self.output_text = ""

    def output_port_scene_pos(self, port: str = "output") -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH, self._height / 2))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath):
        phase = glow_phase()
        cx = NODE_WIDTH / 2
        cy = self._height / 2
        pulse = 0.55 + 0.45 * _math.sin(phase * 2 * _math.pi)
        halo_rect = QRectF(-5, -5, NODE_WIDTH + 10, self._height + 10)
        halo_path = QPainterPath()
        halo_path.addRoundedRect(halo_rect, _CORNER_RADIUS + 5, _CORNER_RADIUS + 5)
        halo_pen = QPen(QColor(58, 142, 245, int(60 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)
        angle_deg = phase * 360.0
        grad = QConicalGradient(cx, cy, angle_deg)
        grad.setColorAt(0.00, QColor(120, 200, 255, 240))
        grad.setColorAt(0.25, QColor(30, 80, 160, 60))
        grad.setColorAt(1.00, QColor(120, 200, 255, 240))
        sweep_pen = QPen(QBrush(grad), 3)
        sweep_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(sweep_pen)
        painter.drawPath(border_path)
        base_pen = QPen(QColor(58, 142, 245, 140), 1.2)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(base_pen)
        painter.drawPath(border_path)

    def paint(self, painter: QPainter, option, widget=None):
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
        painter.fillPath(header_path, QBrush(_SCRIPT_ACCENT))
        painter.restore()

        header_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(header_font)
        painter.setPen(QColor("#dddddd"))
        painter.drawText(
            QRectF(8, 0, NODE_WIDTH - 16, _HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            SCRIPT_NODE_DISPLAY_NAME.upper(),
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
            "script_path": self.script_path,
            "auto_send_enter": self.auto_send_enter,
        }

    def from_dict(self, data: dict):
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        self.script_path = data.get("script_path", "")
        self.auto_send_enter = bool(data.get("auto_send_enter", False))


def ScriptNodeFactory(node_id=None, label_index=1):
    return ScriptNode(node_id=node_id, label_index=label_index)
