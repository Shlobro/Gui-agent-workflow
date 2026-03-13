"""GitActionNode — git operation nodes (add, commit, push) for the workflow canvas."""

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
    glow_phase,
    set_node_status,
    PORT_RADIUS,
    INPUT_PORT_EDGE_COLOR, INPUT_PORT_FILL_COLOR, INPUT_PORT_LABEL_COLOR,
    OUTPUT_PORT_EDGE_COLOR, OUTPUT_PORT_FILL_COLOR, OUTPUT_PORT_LABEL_COLOR,
)
from .llm_widget import NODE_WIDTH

# Accent color per git action (header strip)
_GIT_ACCENT = {
    "git_add":    QColor("#1a5a3a"),
    "git_commit": QColor("#1a3a6a"),
    "git_push":   QColor("#5a1a6a"),
}

GIT_ACTION_DISPLAY_NAMES = {
    "git_add":    "Git Add",
    "git_commit": "Git Commit",
    "git_push":   "Git Push",
}

CORNER_RADIUS = 12
_HEADER_HEIGHT = 28
_COMPACT_GIT_NODE_HEIGHT = 64


class GitActionNode(WorkflowNode):
    """A git-action node whose action type is a mutable instance attribute."""

    node_type = "git_action"

    def __init__(self, node_id: Optional[str] = None, label_index: int = 1):
        super().__init__(node_id=node_id, label_index=label_index)

        self.git_action: str = "git_add"
        self.msg_source: str = "static"
        self.commit_msg: str = ""
        self.commit_msg_file: str = ""
        self._title: str = f"Git Action {label_index}"
        self._height = _COMPACT_GIT_NODE_HEIGHT

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

    # Compatibility shims so canvas code that reads model_id / prompt_text
    # on all nodes doesn't crash (GitActionNode skips LLM validation).
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
        set_node_status(self, status)

    def append_output(self, line: str):
        self.output_text += line + "\n"

    def clear_output(self):
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

    def _paint_running_glow(self, painter: QPainter, border_path: QPainterPath):
        phase = glow_phase()
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
        accent = _GIT_ACCENT.get(self.git_action, QColor("#444444"))
        painter.save()
        painter.setClipRect(QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT))
        header_path = QPainterPath()
        header_path.addRoundedRect(
            QRectF(0, 0, NODE_WIDTH, _HEADER_HEIGHT), CORNER_RADIUS, CORNER_RADIUS
        )
        painter.fillPath(header_path, QBrush(accent))
        painter.restore()

        # Action label in header
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#dddddd"))
        painter.drawText(
            QRectF(8, 0, NODE_WIDTH - 16, _HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            GIT_ACTION_DISPLAY_NAMES.get(self.git_action, "Git").upper(),
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
            self._draw_selection_glow(
                painter,
                QRectF(-2.5, -2.5, NODE_WIDTH + 5.0, self._height + 5.0),
                CORNER_RADIUS + 2.5,
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
            "git_action": self.git_action,
            "msg_source": self.msg_source,
            "commit_msg": self.commit_msg,
            "commit_msg_file": self.commit_msg_file,
        }

    def from_dict(self, data: dict):
        self.node_id = data.get("id", self.node_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self._title = data.get("name", self._title)
        self.git_action = data.get("git_action", "git_add")
        self.msg_source = data.get("msg_source", "static")
        self.commit_msg = data.get("commit_msg", "")
        self.commit_msg_file = data.get("commit_msg_file", "")


# ---------------------------------------------------------------------------
# Factory function used by canvas load/paste and NODE_TYPE_MAP
# ---------------------------------------------------------------------------

def GitActionNodeFactory(node_id=None, label_index=1):
    return GitActionNode(node_id=node_id, label_index=label_index)
