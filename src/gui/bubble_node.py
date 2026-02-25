"""BubbleNode — a draggable node on the workflow canvas."""

import uuid
from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsProxyWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QPlainTextEdit,
    QLabel,
    QSizePolicy,
    QFrame,
)

from src.llm.base_provider import LLMProviderRegistry

if TYPE_CHECKING:
    from .connection_item import ConnectionItem

# Status colors
STATUS_COLORS = {
    "idle":    QColor("#555555"),
    "running": QColor("#3a8ef5"),
    "done":    QColor("#3aaa5a"),
    "error":   QColor("#e05252"),
}

NODE_WIDTH = 420
NODE_HEIGHT = 300
PORT_RADIUS = 7
CORNER_RADIUS = 12


class BubbleWidget(QWidget):
    """Inner Qt widget embedded in the graphics item."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget { background: transparent; color: #e8e8e8; font-size: 12px; }
            QLineEdit {
                background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
                padding: 3px 6px; color: #e8e8e8; font-weight: bold; font-size: 13px;
            }
            QComboBox {
                background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
                padding: 3px 6px; color: #e8e8e8;
            }
            QComboBox QAbstractItemView { background: #2a2a2a; color: #e8e8e8; }
            QPlainTextEdit {
                background: #1e1e1e; border: 1px solid #444; border-radius: 4px;
                padding: 4px; color: #e8e8e8; font-family: monospace; font-size: 11px;
            }
            QLabel { color: #aaaaaa; font-size: 10px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # Title
        self.title_edit = QLineEdit("Bubble")
        self.title_edit.setPlaceholderText("Node name…")
        layout.addWidget(self.title_edit)

        # Model selector
        model_label = QLabel("Model")
        layout.addWidget(model_label)
        self.model_combo = QComboBox()
        self._populate_models()
        layout.addWidget(self.model_combo)

        # Prompt
        prompt_label = QLabel("Prompt  (use {{bubble_name_output}} for upstream output)")
        layout.addWidget(prompt_label)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Enter your prompt here…")
        self.prompt_edit.setFixedHeight(80)
        layout.addWidget(self.prompt_edit)

        # Output (hidden until run)
        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(2)
        out_label = QLabel("Output")
        out_layout.addWidget(out_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setFixedHeight(72)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        self.setFixedWidth(NODE_WIDTH - 20)

    def _populate_models(self):
        self.model_combo.clear()
        for provider in LLMProviderRegistry.all():
            # Separator item with provider name
            self.model_combo.addItem(f"── {provider.display_name} ──")
            idx = self.model_combo.count() - 1
            item = self.model_combo.model().item(idx)
            item.setEnabled(False)
            item.setForeground(QColor("#888888"))
            for model_id, model_name in provider.get_models():
                self.model_combo.addItem(f"  {model_name}", userData=model_id)

    def get_model_id(self) -> Optional[str]:
        return self.model_combo.currentData()

    def set_model_id(self, model_id: str):
        for i in range(self.model_combo.count()):
            if self.model_combo.itemData(i) == model_id:
                self.model_combo.setCurrentIndex(i)
                return

    def show_output(self, visible: bool = True):
        self._output_frame.setVisible(visible)


class BubbleNode(QGraphicsItem):
    """A draggable workflow bubble node."""

    def __init__(self, bubble_id: Optional[str] = None, label_index: int = 1):
        super().__init__()
        self.bubble_id = bubble_id or str(uuid.uuid4())
        self.label_index = label_index
        self.status = "idle"
        self.output_text = ""
        self._connections: List["ConnectionItem"] = []

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

        # Embedded widget
        self._widget = BubbleWidget()
        self._widget.title_edit.setText(f"Bubble {label_index}")
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(self._widget)
        self._proxy.setPos(0, 0)

        # Resize to fit widget
        self._widget.adjustSize()
        self._height = max(NODE_HEIGHT, self._widget.sizeHint().height() + 20)

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
    def model_id(self) -> Optional[str]:
        return self._widget.get_model_id()

    @model_id.setter
    def model_id(self, value: str):
        self._widget.set_model_id(value)

    @property
    def prompt_text(self) -> str:
        return self._widget.prompt_edit.toPlainText()

    @prompt_text.setter
    def prompt_text(self, value: str):
        self._widget.prompt_edit.setPlainText(value)

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
        new_h = max(NODE_HEIGHT, self._widget.sizeHint().height() + 20)
        if new_h != self._height:
            self.prepareGeometryChange()
            self._height = new_h
            self._update_connections()

    # ------------------------------------------------------------------
    # Port positions
    # ------------------------------------------------------------------

    def output_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH, self._height / 2))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self._height / 2))

    def is_near_output_port(self, scene_pos: QPointF) -> bool:
        port = self.output_port_scene_pos()
        return (scene_pos - port).manhattanLength() < PORT_RADIUS * 3

    def is_near_input_port(self, scene_pos: QPointF) -> bool:
        port = self.input_port_scene_pos()
        return (scene_pos - port).manhattanLength() < PORT_RADIUS * 3

    # ------------------------------------------------------------------
    # Connections bookkeeping
    # ------------------------------------------------------------------

    def add_connection(self, conn: "ConnectionItem"):
        self._connections.append(conn)

    def remove_connection(self, conn: "ConnectionItem"):
        if conn in self._connections:
            self._connections.remove(conn)

    def connections(self) -> List["ConnectionItem"]:
        return list(self._connections)

    def _update_connections(self):
        for conn in self._connections:
            conn.update_path()

    # ------------------------------------------------------------------
    # QGraphicsItem overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return QRectF(-PORT_RADIUS, -PORT_RADIUS,
                      NODE_WIDTH + PORT_RADIUS * 2, self._height + PORT_RADIUS * 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._update_connections()
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, self._height), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, QBrush(QColor("#252525")))

        # Border (status-colored)
        color = STATUS_COLORS.get(self.status, STATUS_COLORS["idle"])
        pen_width = 3 if self.isSelected() else 2
        painter.setPen(QPen(color, pen_width))
        painter.drawPath(path)

        # Output port (right)
        painter.setPen(QPen(QColor("#888888"), 1))
        painter.setBrush(QBrush(QColor("#444444")))
        painter.drawEllipse(QPointF(NODE_WIDTH, self._height / 2), PORT_RADIUS, PORT_RADIUS)

        # Input port (left)
        painter.drawEllipse(QPointF(0, self._height / 2), PORT_RADIUS, PORT_RADIUS)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "id": self.bubble_id,
            "label_index": self.label_index,
            "x": pos.x(),
            "y": pos.y(),
            "name": self.title,
            "model": self.model_id or "",
            "prompt": self.prompt_text,
        }

    def from_dict(self, data: dict):
        self.bubble_id = data.get("id", self.bubble_id)
        self.label_index = data.get("label_index", self.label_index)
        self.setPos(data.get("x", 0), data.get("y", 0))
        self.title = data.get("name", f"Bubble {self.label_index}")
        if data.get("model"):
            self.model_id = data["model"]
        self.prompt_text = data.get("prompt", "")
