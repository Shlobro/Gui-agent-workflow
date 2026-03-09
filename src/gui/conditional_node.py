"""ConditionalNode - routes execution to a true or false branch based on a condition."""

import os
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

# Port colors for true/false output ports
_TRUE_PORT_EDGE_COLOR = QColor("#3aaa5a")
_TRUE_PORT_FILL_COLOR = QColor("#0f3020")
_FALSE_PORT_EDGE_COLOR = QColor("#e05252")
_FALSE_PORT_FILL_COLOR = QColor("#3b1010")

# Header colors
_HEADER_COLOR = QColor("#7a5a1a")
_HEADER_TEXT_COLOR = QColor("#ffd060")
_HEADER_HEIGHT = 28

# Taller than compact LLM nodes to fit two labeled ports
_CONDITIONAL_NODE_HEIGHT = 80


# ---------------------------------------------------------------------------
# Condition registry
# ---------------------------------------------------------------------------

def _check_file_empty(resolved_path: str) -> bool:
    """Return True if the file at the already-resolved absolute path does not exist or is empty."""
    return not os.path.exists(resolved_path) or os.path.getsize(resolved_path) == 0


CONDITION_REGISTRY: dict = {
    "file_empty": {
        "display_name": "Is File Empty",
        "requires_filename": True,
        "execution_mode": "sync",
        "note": "",
        "evaluator": lambda resolved_path, _working_directory: _check_file_empty(
            resolved_path or ""
        ),
    },
    "git_changes": {
        "display_name": "Has Git Changes",
        "requires_filename": False,
        "execution_mode": "git_worker",
        "note": "Checks the selected project folder for staged, unstaged, or untracked git changes.",
    },
}


def condition_execution_mode(condition_type: str) -> str:
    """Return the execution mode for the given condition type ('sync' or 'git_worker')."""
    entry = CONDITION_REGISTRY.get(condition_type)
    return str(entry.get("execution_mode", "sync")) if entry else "sync"


def condition_requires_filename(condition_type: str) -> bool:
    entry = CONDITION_REGISTRY.get(condition_type)
    return bool(entry and entry.get("requires_filename"))


def condition_note(condition_type: str) -> str:
    entry = CONDITION_REGISTRY.get(condition_type)
    if not entry:
        return ""
    return str(entry.get("note", ""))


def condition_display_name(condition_type: str) -> str:
    entry = CONDITION_REGISTRY.get(condition_type)
    if not entry:
        return condition_type
    return str(entry.get("display_name", condition_type))


# ---------------------------------------------------------------------------
# ConditionalNode
# ---------------------------------------------------------------------------

class ConditionalNode(WorkflowNode):
    """A node with two output ports (true/false) that routes based on a condition."""

    node_type = "conditional"   # class-level constant for serialization

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)

        self._title: str = f"Condition {label_index}"
        self._filename: str = ""
        self.condition_type: str = "file_empty"
        self._height = _CONDITIONAL_NODE_HEIGHT

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

    # Compatibility shims - ConditionalNode is not an LLM node
    @property
    def model_id(self) -> Optional[str]:
        return None

    @property
    def prompt_text(self) -> str:
        return ""

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def evaluate(self, resolved_path: Optional[str], working_directory: str) -> bool:
        """Evaluate the condition against the current execution context."""
        entry = CONDITION_REGISTRY.get(self.condition_type)
        if entry is None:
            raise ValueError(f"Unknown condition type: {self.condition_type!r}")
        evaluator = entry.get("evaluator")
        if evaluator is None:
            raise ValueError(f"Condition type {self.condition_type!r} requires async evaluation.")
        return bool(evaluator(resolved_path, working_directory))

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
    # Port positions - two output ports on the right edge
    # ------------------------------------------------------------------

    def output_port_scene_pos(self, port: str = "output") -> QPointF:
        """Return scene position of the named output port.

        port="true"  -> upper-right at 33% height
        port="false" -> lower-right at 67% height
        port="output" -> center (same as true, used as a fallback)
        """
        if port == "true":
            y = self._height * 0.33
        elif port == "false":
            y = self._height * 0.67
        else:
            y = self._height * 0.33  # default to true port position
        return self.mapToScene(QPointF(NODE_WIDTH, y))

    def true_port_scene_pos(self) -> QPointF:
        return self.output_port_scene_pos("true")

    def false_port_scene_pos(self) -> QPointF:
        return self.output_port_scene_pos("false")

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    # ------------------------------------------------------------------
    # Port proximity helpers - separate methods for each output port
    # ------------------------------------------------------------------

    def is_near_true_port(self, scene_pos: QPointF) -> bool:
        return (scene_pos - self.true_port_scene_pos()).manhattanLength() < PORT_RADIUS * 3

    def is_near_false_port(self, scene_pos: QPointF) -> bool:
        return (scene_pos - self.false_port_scene_pos()).manhattanLength() < PORT_RADIUS * 3

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        """Returns True if near either output port (for generic node scanning)."""
        return self.is_near_true_port(scene_pos) or self.is_near_false_port(scene_pos)

    def _has_true_connection(self) -> bool:
        return any(
            conn.source_node is self and getattr(conn, "source_port", "output") == "true"
            for conn in self._connections
        )

    def _has_false_connection(self) -> bool:
        return any(
            conn.source_node is self and getattr(conn, "source_port", "output") == "false"
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
        halo_pen = QPen(QColor(245, 200, 58, int(60 * pulse)), 10)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        painter.drawPath(halo_path)
        angle_deg = phase * 360.0
        grad = QConicalGradient(cx, cy, angle_deg)
        grad.setColorAt(0.00, QColor(255, 220, 100, 240))
        grad.setColorAt(0.25, QColor(200, 160, 30, 60))
        grad.setColorAt(1.00, QColor(255, 220, 100, 240))
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
            "CONDITION",
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
            outer_glow_pen = QPen(QColor(255, 200, 60, 90), 8)
            outer_glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outer_glow_pen)
            painter.drawPath(glow_path)
            inner_glow_pen = QPen(QColor(255, 220, 100, 220), 3)
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

        # True port (upper right, ~33%)
        true_y = self._height * 0.33
        painter.setPen(QPen(_TRUE_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(_TRUE_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(NODE_WIDTH, true_y), PORT_RADIUS, PORT_RADIUS)

        # "T" label next to true port
        small_font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(small_font)
        painter.setPen(_TRUE_PORT_EDGE_COLOR)
        painter.drawText(
            QRectF(NODE_WIDTH - 22, true_y - 8, 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            "T",
        )

        if not self._has_true_connection():
            self._draw_port_direction_arrow(
                painter,
                start_x=NODE_WIDTH - 6.0,
                tip_x=NODE_WIDTH + 6.0,
                y=true_y,
                color=_TRUE_PORT_EDGE_COLOR,
            )

        # False port (lower right, ~67%)
        false_y = self._height * 0.67
        painter.setPen(QPen(_FALSE_PORT_EDGE_COLOR, 1.4))
        painter.setBrush(QBrush(_FALSE_PORT_FILL_COLOR))
        painter.drawEllipse(QPointF(NODE_WIDTH, false_y), PORT_RADIUS, PORT_RADIUS)

        # "F" label next to false port
        painter.setPen(_FALSE_PORT_EDGE_COLOR)
        painter.drawText(
            QRectF(NODE_WIDTH - 22, false_y - 8, 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            "F",
        )

        if not self._has_false_connection():
            self._draw_port_direction_arrow(
                painter,
                start_x=NODE_WIDTH - 6.0,
                tip_x=NODE_WIDTH + 6.0,
                y=false_y,
                color=_FALSE_PORT_EDGE_COLOR,
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
            "condition_type": self.condition_type,
        }

    def from_dict(self, data: dict) -> None:
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        self._filename = data.get("filename", "")
        self.condition_type = data.get("condition_type", "file_empty")


# ---------------------------------------------------------------------------
# Factory function for NODE_TYPE_MAP
# ---------------------------------------------------------------------------

def ConditionalNodeFactory(node_id=None, label_index=1):
    return ConditionalNode(node_id=node_id, label_index=label_index)
