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
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsProxyWidget,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
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
NODE_HEIGHT = 160
_HEADER_HEIGHT = 28


# ---------------------------------------------------------------------------
# Embedded widget
# ---------------------------------------------------------------------------

class FileOpWidget(QWidget):
    """Slim widget embedded inside a FileOpNode — title + filename input + output area."""

    _STYLESHEET = """
        QWidget#file_op_widget_root {
            background: transparent;
            color: #e8e8e8;
            font-size: 12px;
        }
        QLineEdit {
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            padding: 3px 6px; color: #e8e8e8; font-weight: bold; font-size: 13px;
        }
        QPlainTextEdit {
            background: #1e1e1e; border: 1px solid #444; border-radius: 4px;
            padding: 4px; color: #e8e8e8; font-family: monospace; font-size: 11px;
        }
        QLabel { color: #aaaaaa; font-size: 10px; }
    """

    def __init__(self, op_label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("file_op_widget_root")
        self.setStyleSheet(self._STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # Title (node name, editable)
        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit(op_label)
        self.title_edit.setPlaceholderText("Node name…")
        layout.addWidget(self.title_edit)

        # Filename input
        fn_label = QLabel("Filename")
        layout.addWidget(fn_label)
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("e.g. output.txt")
        layout.addWidget(self.filename_edit)

        # Output area (hidden until execution)
        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(2)
        out_label = QLabel("Result")
        out_layout.addWidget(out_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setFixedHeight(52)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        self.setFixedWidth(NODE_WIDTH - 20)

    def show_output(self, visible: bool = True):
        self._output_frame.setVisible(visible)


# ---------------------------------------------------------------------------
# Base graphics item
# ---------------------------------------------------------------------------

class FileOpNode(WorkflowNode):
    """Base class for file-operation nodes. Subclasses set `node_type`."""

    node_type: str = ""   # overridden by subclasses

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)

        op_label = NODE_TYPE_DISPLAY_NAMES.get(self.node_type, "File Op")
        self._widget = FileOpWidget(op_label)
        self._widget.title_edit.setText(f"{op_label} {label_index}")
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(self._widget)
        self._proxy.setPos(0, _HEADER_HEIGHT)  # below the painted header strip

        self._widget.adjustSize()
        self._height = max(NODE_HEIGHT, self._widget.sizeHint().height() + _HEADER_HEIGHT + 8)

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
    def filename(self) -> str:
        return self._widget.filename_edit.text()

    @filename.setter
    def filename(self, value: str):
        self._widget.filename_edit.setText(value)

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
        new_h = max(NODE_HEIGHT, self._widget.sizeHint().height() + _HEADER_HEIGHT + 8)
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
            "name": self.title,
            "filename": self.filename,
        }

    def from_dict(self, data: dict):
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self.title = data.get("name", self.title)
        self.filename = data.get("filename", "")


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
