"""ConnectionItem — a directed arrow between two BubbleNodes."""

import heapq
import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem

from .bubble_node import BubbleNode, PORT_RADIUS

ARROW_SIZE = 10
PORT_EDGE_OFFSET = PORT_RADIUS + 2
PORT_GUARD_OFFSET = 38
OBSTACLE_PADDING = 12
BASE_GRID_SIZE = 24.0
MAX_GRID_DIMENSION = 180
ROUTE_PADDING = 120.0
CORRIDOR_MARGIN = 260.0
GridCell = Tuple[int, int]


class ConnectionItem(QGraphicsPathItem):
    """Obstacle-aware routed arrow from source output port to target input port."""

    def __init__(self, source: BubbleNode, target: BubbleNode):
        super().__init__()
        self.source_bubble = source
        self.target_bubble = target
        self._arrow_tip = QPointF()
        self._arrow_angle = 0.0

        self.setZValue(0)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)

        source.add_connection(self)
        target.add_connection(self)

        self.update_path()

    def update_path(self):
        src_center = self.source_bubble.output_port_scene_pos()
        dst_center = self.target_bubble.input_port_scene_pos()

        src_edge = src_center + QPointF(PORT_EDGE_OFFSET, 0)
        dst_edge = dst_center - QPointF(PORT_EDGE_OFFSET, 0)
        src_guard = src_edge + QPointF(PORT_GUARD_OFFSET, 0)
        dst_guard = dst_edge - QPointF(PORT_GUARD_OFFSET, 0)

        routed = self._route_points(src_guard, dst_guard, self._obstacle_rects())
        if not routed:
            routed = [src_guard, dst_guard]

        points = self._compress_points([src_edge, *routed, dst_edge])
        if len(points) < 2:
            points = [src_edge, dst_edge]

        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        self.setPath(path)

        self._set_arrow_geometry(points)
        self.update()

    def _obstacle_rects(self) -> List[QRectF]:
        scene = self.scene()
        if scene is None:
            return []

        obstacles: List[QRectF] = []
        for item in scene.items():
            if not isinstance(item, BubbleNode):
                continue
            rect = item.mapRectToScene(item.boundingRect())
            if rect.isNull():
                continue
            obstacles.append(
                rect.adjusted(
                    -OBSTACLE_PADDING,
                    -OBSTACLE_PADDING,
                    OBSTACLE_PADDING,
                    OBSTACLE_PADDING,
                )
            )
        return obstacles

    def _route_points(
        self,
        start: QPointF,
        end: QPointF,
        obstacles: List[QRectF],
    ) -> Optional[List[QPointF]]:
        relevant_obstacles = self._relevant_obstacles(start, end, obstacles)
        bounds = self._route_bounds(start, end, relevant_obstacles)
        width = max(1.0, bounds.width())
        height = max(1.0, bounds.height())

        grid_size = max(
            BASE_GRID_SIZE,
            width / max(1, MAX_GRID_DIMENSION - 1),
            height / max(1, MAX_GRID_DIMENSION - 1),
        )
        x_count = int(math.ceil(width / grid_size)) + 1
        y_count = int(math.ceil(height / grid_size)) + 1
        if x_count <= 1 or y_count <= 1:
            return [start, end]

        left = bounds.left()
        top = bounds.top()

        def to_cell(point: QPointF) -> GridCell:
            gx = int(round((point.x() - left) / grid_size))
            gy = int(round((point.y() - top) / grid_size))
            gx = max(0, min(x_count - 1, gx))
            gy = max(0, min(y_count - 1, gy))
            return gx, gy

        def to_point(cell: GridCell) -> QPointF:
            return QPointF(
                left + (cell[0] * grid_size),
                top + (cell[1] * grid_size),
            )

        blocked = set()
        half = grid_size * 0.5
        for gx in range(x_count):
            x = left + (gx * grid_size)
            for gy in range(y_count):
                y = top + (gy * grid_size)
                cell_rect = QRectF(x - half, y - half, grid_size, grid_size)
                if any(rect.intersects(cell_rect) for rect in relevant_obstacles):
                    blocked.add((gx, gy))

        start_cell = to_cell(start)
        end_cell = to_cell(end)
        blocked.discard(start_cell)
        blocked.discard(end_cell)

        cell_path = self._astar_path(start_cell, end_cell, blocked, x_count, y_count)
        if not cell_path:
            return None

        points = [start]
        points.extend(to_point(cell) for cell in cell_path[1:-1])
        points.append(end)
        return self._compress_points(points)

    @staticmethod
    def _route_bounds(start: QPointF, end: QPointF, obstacles: List[QRectF]) -> QRectF:
        left = min(start.x(), end.x())
        right = max(start.x(), end.x())
        top = min(start.y(), end.y())
        bottom = max(start.y(), end.y())

        for rect in obstacles:
            left = min(left, rect.left())
            right = max(right, rect.right())
            top = min(top, rect.top())
            bottom = max(bottom, rect.bottom())

        return QRectF(left, top, right - left, bottom - top).adjusted(
            -ROUTE_PADDING,
            -ROUTE_PADDING,
            ROUTE_PADDING,
            ROUTE_PADDING,
        )

    @staticmethod
    def _relevant_obstacles(
        start: QPointF,
        end: QPointF,
        obstacles: List[QRectF],
    ) -> List[QRectF]:
        corridor = QRectF(
            min(start.x(), end.x()),
            min(start.y(), end.y()),
            abs(end.x() - start.x()),
            abs(end.y() - start.y()),
        )
        corridor = corridor.adjusted(
            -CORRIDOR_MARGIN,
            -CORRIDOR_MARGIN,
            CORRIDOR_MARGIN,
            CORRIDOR_MARGIN,
        )
        relevant = [rect for rect in obstacles if rect.intersects(corridor)]
        return relevant or obstacles

    @staticmethod
    def _astar_path(
        start: GridCell,
        goal: GridCell,
        blocked: set,
        x_count: int,
        y_count: int,
    ) -> Optional[List[GridCell]]:
        if start == goal:
            return [start]

        def heuristic(a: GridCell, b: GridCell) -> int:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        open_heap = [(heuristic(start, goal), 0, start)]
        came_from = {}
        g_score = {start: 0}
        closed = set()
        serial = 0
        directions = ((1, 0), (-1, 0), (0, 1), (0, -1))

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            closed.add(current)

            for dx, dy in directions:
                nxt = (current[0] + dx, current[1] + dy)
                if not (0 <= nxt[0] < x_count and 0 <= nxt[1] < y_count):
                    continue
                if nxt in blocked:
                    continue

                tentative = g_score[current] + 1
                if tentative >= g_score.get(nxt, math.inf):
                    continue

                came_from[nxt] = current
                g_score[nxt] = tentative
                serial += 1
                priority = tentative + heuristic(nxt, goal)
                heapq.heappush(open_heap, (priority, serial, nxt))

        return None

    @staticmethod
    def _compress_points(points: List[QPointF]) -> List[QPointF]:
        if not points:
            return []

        deduped = [points[0]]
        for point in points[1:]:
            if (point - deduped[-1]).manhattanLength() < 0.01:
                continue
            deduped.append(point)

        if len(deduped) < 3:
            return deduped

        result = [deduped[0]]
        for idx in range(1, len(deduped) - 1):
            prev = result[-1]
            cur = deduped[idx]
            nxt = deduped[idx + 1]
            same_x = abs(prev.x() - cur.x()) < 0.01 and abs(cur.x() - nxt.x()) < 0.01
            same_y = abs(prev.y() - cur.y()) < 0.01 and abs(cur.y() - nxt.y()) < 0.01
            if same_x or same_y:
                continue
            result.append(cur)
        result.append(deduped[-1])
        return result

    def _set_arrow_geometry(self, points: List[QPointF]):
        if len(points) < 2:
            self._arrow_tip = points[0] if points else QPointF()
            self._arrow_angle = 0.0
            return

        tip = points[-1]
        prev = points[-2]
        if (tip - prev).manhattanLength() < 0.01:
            prev = points[0]

        self._arrow_tip = tip
        self._arrow_angle = math.atan2(tip.y() - prev.y(), tip.x() - prev.x())

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor("#888888")
        if self.isSelected():
            color = QColor("#ffcc44")

        pen = QPen(color, 2, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        p1 = QPointF(
            self._arrow_tip.x() - ARROW_SIZE * math.cos(self._arrow_angle - math.pi / 6),
            self._arrow_tip.y() - ARROW_SIZE * math.sin(self._arrow_angle - math.pi / 6),
        )
        p2 = QPointF(
            self._arrow_tip.x() - ARROW_SIZE * math.cos(self._arrow_angle + math.pi / 6),
            self._arrow_tip.y() - ARROW_SIZE * math.sin(self._arrow_angle + math.pi / 6),
        )
        arrow = QPolygonF([self._arrow_tip, p1, p2])
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
