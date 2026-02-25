"""ConnectionItem — a directed arrow between two BubbleNodes."""

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem

if TYPE_CHECKING:
    from .bubble_node import BubbleNode

ARROW_SIZE = 10


class ConnectionItem(QGraphicsPathItem):
    """Bezier arrow from source bubble's output port to target bubble's input port."""

    def __init__(self, source: "BubbleNode", target: "BubbleNode"):
        super().__init__()
        self.source_bubble = source
        self.target_bubble = target

        self.setZValue(0)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)

        source.add_connection(self)
        target.add_connection(self)

        self.update_path()

    def update_path(self):
        src = self.source_bubble.output_port_scene_pos()
        dst = self.target_bubble.input_port_scene_pos()

        dx = abs(dst.x() - src.x()) * 0.5

        path = QPainterPath()
        path.moveTo(src)
        path.cubicTo(
            QPointF(src.x() + dx, src.y()),
            QPointF(dst.x() - dx, dst.y()),
            dst,
        )
        self.setPath(path)
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor("#888888")
        if self.isSelected():
            color = QColor("#ffcc44")

        pen = QPen(color, 2, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        # Arrow head at destination
        dst = self.target_bubble.input_port_scene_pos()
        src = self.source_bubble.output_port_scene_pos()
        dx = abs(dst.x() - src.x()) * 0.5
        # Tangent at the end of the cubic: control point 2 → dst
        ctrl2 = QPointF(dst.x() - dx, dst.y())
        angle = math.atan2(dst.y() - ctrl2.y(), dst.x() - ctrl2.x())

        p1 = QPointF(
            dst.x() - ARROW_SIZE * math.cos(angle - math.pi / 6),
            dst.y() - ARROW_SIZE * math.sin(angle - math.pi / 6),
        )
        p2 = QPointF(
            dst.x() - ARROW_SIZE * math.cos(angle + math.pi / 6),
            dst.y() - ARROW_SIZE * math.sin(angle + math.pi / 6),
        )
        arrow = QPolygonF([dst, p1, p2])
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 1))
        painter.drawPolygon(arrow)

    def detach(self):
        """Remove this connection from both bubble bookkeeping lists."""
        self.source_bubble.remove_connection(self)
        self.target_bubble.remove_connection(self)

    def to_dict(self) -> dict:
        return {
            "from": self.source_bubble.bubble_id,
            "to": self.target_bubble.bubble_id,
        }
