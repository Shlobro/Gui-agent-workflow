"""FileOpNode — file-operation nodes (create, truncate, delete) for the workflow canvas."""

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
    OUTPUT_PORT_EDGE_COLOR, OUTPUT_PORT_FILL_COLOR, OUTPUT_PORT_LABEL_COLOR,
)
from .llm_widget import NODE_WIDTH

# Accent color per operation type (header strip)
_OP_ACCENT = {
    "create_file":   QColor("#2a7a2a"),
    "truncate_file": QColor("#7a6a1a"),
    "delete_file":   QColor("#7a2a2a"),
}

NODE_TYPE_DISPLAY_NAMES = {
    "create_file":   "Create File",
    "truncate_file": "Truncate File",
    "delete_file":   "Delete File",
}

CORNER_RADIUS = 12
_HEADER_HEIGHT = 28

# Compact node height (header + title row + padding)
_COMPACT_FILE_NODE_HEIGHT = 64


# ---------------------------------------------------------------------------
# Base graphics item
# ---------------------------------------------------------------------------

class FileOpNode(WorkflowNode):
    """Base class for file-operation nodes. Subclasses set `node_type`."""

    node_type: str = ""   # overridden by subclasses

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)

        op_label = NODE_TYPE_DISPLAY_NAMES.get(self.node_type, "File Op")
        self._title: str = f"{op_label} {label_index}"
        self._filename: str = ""
        self._height = _COMPACT_FILE_NODE_HEIGHT

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
    def filename(self) -> str:
        return self._filename

    @filename.setter
    def filename(self, value: str):
        self._filename = value

    # Compatibility shims so canvas code that reads model_id / prompt_text
    # on all nodes doesn't crash (FileOpNode skips LLM validation instead).
    @property
    def model_id(self) -> Optional[str]:
        return None

    @property
    def prompt_text(self) -> str:
        return ""

    # ------------------------------------------------------------------
    # Status / output
    # ------------------------------------------------------------------

    def set_status(self, status: str):
        self.status = status
        self.update()

    def append_output(self, line: str):
        self.output_text += line + "\n"

    def clear_output(self):
        self.output_text = ""

    # ------------------------------------------------------------------
    # Port positions
    # ------------------------------------------------------------------

    def output_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH, self._height / 2))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath):
        phase = (id(self) * 0.001) % 1.0   # static stand-in; canvas drives repaints via set_status
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
        path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, self._height), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, QBrush(QColor("#252525")))

        # Accent header strip — rounded top corners, flat bottom edge.
        accent = _OP_ACCENT.get(self.node_type, QColor("#444444"))
        painter.save()
        painter.setClipRect(QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT))
        header_path = QPainterPath()
        header_path.addRoundedRect(
            QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT), CORNER_RADIUS, CORNER_RADIUS
        )
        painter.fillPath(header_path, QBrush(accent))
        painter.restore()

        # Op type label in header
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#dddddd"))
        painter.drawText(
            QRectF(8, 0, NODE_WIDTH - 16, _HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            NODE_TYPE_DISPLAY_NAMES.get(self.node_type, "File Op").upper(),
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
            "node_type": self.node_type,
            "id": self.node_id,
            "label_index": self.label_index,
            "x": pos.x(),
            "y": pos.y(),
            "name": self._title,
            "filename": self._filename,
        }

    def from_dict(self, data: dict):
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        self._filename = data.get("filename", "")


# ---------------------------------------------------------------------------
# Concrete subclasses
# ---------------------------------------------------------------------------

class CreateFileNode(FileOpNode):
    node_type = "create_file"


class TruncateFileNode(FileOpNode):
    node_type = "truncate_file"


class DeleteFileNode(FileOpNode):
    node_type = "delete_file"


# ---------------------------------------------------------------------------
# Lookup map used by canvas load/paste
# ---------------------------------------------------------------------------

NODE_TYPE_MAP = {
    "create_file":   CreateFileNode,
    "truncate_file": TruncateFileNode,
    "delete_file":   DeleteFileNode,
}
