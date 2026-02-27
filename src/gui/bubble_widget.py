"""BubbleWidget — embedded Qt widget inside a BubbleNode graphics item."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.llm.base_provider import LLMProviderRegistry

NODE_WIDTH = 420
ICON_SIZE = 16

LOGO_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
PROVIDER_LOGO_FILES = {
    "claude": "claude_logo.png",
    "codex": "openai_logo.png",
    "gemini": "gemini_logo.png",
}
PROVIDER_ICON_CACHE: dict = {}


class _ModelListWidget(QListWidget):
    """List widget that notifies when it loses focus."""

    def __init__(self, on_focus_lost, parent=None):
        super().__init__(parent)
        self._on_focus_lost = on_focus_lost

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._on_focus_lost:
            self._on_focus_lost()


class ModelSelector(QWidget):
    """Compact model selector with dropdown overlay on the canvas viewport."""

    model_changed = Signal(str, str)

    LIST_STYLESHEET = """
        QListWidget {
            background: #2a2a2a;
            color: #e8e8e8;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 2px;
            outline: 0px;
        }
        QListWidget::item {
            padding: 4px 6px;
        }
        QListWidget::item:selected {
            background: #3a8ef5;
            color: #ffffff;
        }
        QListWidget::item:hover {
            background: #324056;
        }
    """

    def __init__(self, popup_parent: QWidget, on_layout_change=None, parent=None):
        super().__init__(parent)
        self._on_layout_change = on_layout_change
        self._popup_parent = popup_parent
        self._current_model_id: Optional[str] = None
        self._current_label = "Select model"
        self._dropdown_height = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toggle_button = QPushButton()
        self._toggle_button.setCheckable(True)
        self._toggle_button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._toggle_button.setMinimumHeight(26)
        self._toggle_button.setToolTip("Choose model")
        self._toggle_button.clicked.connect(self._on_toggle_clicked)
        layout.addWidget(self._toggle_button)

        self._list = _ModelListWidget(self._close_dropdown, popup_parent)
        self._list.setObjectName("model_selector_dropdown")
        self._list.setVisible(False)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.setStyleSheet(self.LIST_STYLESHEET)

        self._update_button_label()

    def clear(self):
        self._list.clear()
        self._current_model_id = None
        self._current_label = "Select model"
        self._close_dropdown()
        self._update_button_label()
        self._update_list_height()

    def add_model(self, icon: QIcon, model_name: str, model_id: str, company_name: str):
        item = QListWidgetItem(icon, model_name)
        item.setData(Qt.ItemDataRole.UserRole, model_id)
        item.setToolTip(company_name)
        self._list.addItem(item)
        self._update_list_height()

        if self._current_model_id is None:
            self._select_item(item)

    def current_model_id(self) -> Optional[str]:
        return self._current_model_id

    def set_model_id(self, model_id: str):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == model_id:
                self._select_item(item)
                return

    def set_enabled(self, enabled: bool):
        self._toggle_button.setEnabled(enabled)
        self._list.setEnabled(enabled)
        if not enabled:
            self._close_dropdown()
            self._update_button_label()

    def _on_toggle_clicked(self):
        if self._toggle_button.isChecked():
            self._open_dropdown()
            return
        self._close_dropdown()

    def _on_item_clicked(self, item: QListWidgetItem):
        self._select_item(item)
        self._close_dropdown()

    def _select_item(self, item: QListWidgetItem):
        old_id = self._current_model_id
        self._list.setCurrentItem(item)
        self._current_model_id = item.data(Qt.ItemDataRole.UserRole)
        self._current_label = item.text()
        self._toggle_button.setIcon(item.icon())
        self._update_button_label()
        if old_id is not None and old_id != self._current_model_id:
            self.model_changed.emit(old_id, self._current_model_id)

    def _update_button_label(self):
        self._toggle_button.setText(self._current_label)

    def _update_list_height(self):
        if self._list.count() == 0:
            self._dropdown_height = 0
            return

        visible_rows = min(self._list.count(), 10)
        row_h = self._list.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 24

        frame = self._list.frameWidth() * 2
        self._dropdown_height = frame + (visible_rows * row_h) + 2

    def _open_dropdown(self):
        if self._list.count() == 0 or self._dropdown_height <= 0:
            self._toggle_button.setChecked(False)
            return
        self._ensure_overlay_parent()
        self._position_dropdown()
        self._list.show()
        self._list.raise_()
        self._list.setFocus(Qt.FocusReason.MouseFocusReason)

    def _close_dropdown(self):
        if not hasattr(self, "_list"):
            return
        self._list.hide()
        if self._toggle_button.isChecked():
            self._toggle_button.blockSignals(True)
            self._toggle_button.setChecked(False)
            self._toggle_button.blockSignals(False)

    def _position_dropdown(self):
        overlay_parent = self._overlay_parent()
        button_rect = self._button_rect_in_overlay(overlay_parent)

        width = max(120, button_rect.width())
        width = min(width, max(120, overlay_parent.width() - 16))

        button_bottom_y = button_rect.y() + button_rect.height() + 2

        x = button_rect.x()
        x = max(8, min(x, overlay_parent.width() - width - 8))

        frame = self._list.frameWidth() * 2
        row_h = self._list.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 24
        min_rows = min(3, max(1, self._list.count()))
        min_height = frame + (row_h * min_rows) + 2

        down_space = max(0, overlay_parent.height() - button_bottom_y - 8)
        up_space = max(0, button_rect.y() - 10)

        place_below = down_space >= min_height or down_space >= up_space
        if place_below:
            height = min(self._dropdown_height, down_space)
            if height < min_height and up_space > down_space:
                place_below = False
        if not place_below:
            height = min(self._dropdown_height, up_space)
            y = button_rect.y() - height - 2
            y = max(8, y)
        else:
            y = button_bottom_y

        if height <= 0:
            self._close_dropdown()
            return

        self._list.setGeometry(x, y, width, height)

    def _resolve_canvas_view(self) -> Optional[QGraphicsView]:
        proxy = self._popup_parent.graphicsProxyWidget()
        if proxy is None:
            return None

        scene = proxy.scene()
        if scene is None:
            return None

        views = scene.views()
        if not views:
            return None
        return views[0]

    def _button_rect_in_overlay(self, overlay_parent: QWidget) -> QRect:
        view = self._resolve_canvas_view()
        if view is not None and overlay_parent is view.viewport():
            proxy = self._popup_parent.graphicsProxyWidget()
            if proxy is not None:
                button_rect_proxy = proxy.subWidgetRect(self._toggle_button)
                scene_top_left = proxy.mapToScene(button_rect_proxy.topLeft())
                scene_bottom_right = proxy.mapToScene(button_rect_proxy.bottomRight())
                top_left = view.mapFromScene(scene_top_left)
                bottom_right = view.mapFromScene(scene_bottom_right)

                left = min(top_left.x(), bottom_right.x())
                top = min(top_left.y(), bottom_right.y())
                width = max(1, abs(bottom_right.x() - top_left.x()))
                height = max(1, abs(bottom_right.y() - top_left.y()))
                return QRect(left, top, width, height)

        top_left_global = self._toggle_button.mapToGlobal(QPoint(0, 0))
        bottom_right_global = self._toggle_button.mapToGlobal(
            QPoint(self._toggle_button.width(), self._toggle_button.height())
        )
        top_left = overlay_parent.mapFromGlobal(top_left_global)
        bottom_right = overlay_parent.mapFromGlobal(bottom_right_global)
        left = min(top_left.x(), bottom_right.x())
        top = min(top_left.y(), bottom_right.y())
        width = max(1, abs(bottom_right.x() - top_left.x()))
        height = max(1, abs(bottom_right.y() - top_left.y()))
        return QRect(left, top, width, height)

    def _overlay_parent(self) -> QWidget:
        view = self._resolve_canvas_view()
        if view is not None:
            return view.viewport()

        active_window = QApplication.activeWindow()
        if isinstance(active_window, QWidget):
            return active_window
        window = self._popup_parent.window()
        if isinstance(window, QWidget):
            return window
        return self._popup_parent

    def _ensure_overlay_parent(self):
        overlay_parent = self._overlay_parent()
        if self._list.parentWidget() is overlay_parent:
            return
        self._list.hide()
        self._list.setParent(overlay_parent)
        self._list.setStyleSheet(self.LIST_STYLESHEET)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_list") and self._list.isVisible():
            self._position_dropdown()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_list") and self._list.isVisible():
            self._position_dropdown()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._close_dropdown()


class BubbleWidget(QWidget):
    """Inner Qt widget embedded in the graphics item."""

    def __init__(self, on_layout_change=None, parent=None):
        super().__init__(parent)
        self.setObjectName("bubble_widget_root")
        self.setStyleSheet("""
            QWidget#bubble_widget_root {
                background: transparent;
                color: #e8e8e8;
                font-size: 12px;
            }
            QLineEdit {
                background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
                padding: 3px 6px; color: #e8e8e8; font-weight: bold; font-size: 13px;
            }
            QPushButton {
                background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
                padding: 4px 8px; color: #e8e8e8; text-align: left;
            }
            QPushButton:hover { border: 1px solid #555; }
            QPushButton:pressed { background: #222222; }
            QListWidget {
                background: #2a2a2a;
                color: #e8e8e8;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 2px;
                outline: 0px;
            }
            QListWidget::item {
                padding: 4px 6px;
            }
            QListWidget::item:selected {
                background: #3a8ef5;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background: #324056;
            }
            QPlainTextEdit {
                background: #1e1e1e; border: 1px solid #444; border-radius: 4px;
                padding: 4px; color: #e8e8e8; font-family: monospace; font-size: 11px;
            }
            QLabel { color: #aaaaaa; font-size: 10px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        self.title_edit = QLineEdit("Bubble")
        self.title_edit.setPlaceholderText("Node name…")
        layout.addWidget(self.title_edit)

        model_label = QLabel("Model")
        layout.addWidget(model_label)
        self.model_selector = ModelSelector(
            popup_parent=self,
            on_layout_change=on_layout_change,
        )
        self._populate_models()
        layout.addWidget(self.model_selector)

        prompt_label = QLabel("Prompt")
        layout.addWidget(prompt_label)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Enter your prompt here…")
        self.prompt_edit.setFixedHeight(80)
        layout.addWidget(self.prompt_edit)

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
        self.model_selector.clear()
        providers = self._get_registered_providers()
        first_model_index = -1
        model_rows = 0

        for provider in providers:
            icon = self._provider_icon(provider.name)
            company_name = self._provider_company(provider.name)
            for model_id, model_name in provider.get_models():
                self.model_selector.add_model(icon, model_name, model_id, company_name)
                if first_model_index < 0:
                    first_model_index = model_rows
                model_rows += 1

        if first_model_index >= 0:
            self.model_selector.set_enabled(True)
            return

        self.model_selector.clear()
        self.model_selector.set_enabled(False)

    @staticmethod
    def _provider_company(provider_name: str) -> str:
        return {
            "claude": "Anthropic",
            "codex": "OpenAI",
            "gemini": "Google Gemini",
        }.get(provider_name, provider_name.title())

    @staticmethod
    def _get_registered_providers():
        providers = LLMProviderRegistry.all()
        if providers:
            return providers

        import src.llm  # noqa: F401

        return LLMProviderRegistry.all()

    @staticmethod
    def _provider_icon(provider_name: str) -> QIcon:
        if provider_name in PROVIDER_ICON_CACHE:
            return PROVIDER_ICON_CACHE[provider_name]

        logo_filename = PROVIDER_LOGO_FILES.get(provider_name)
        if logo_filename:
            logo_path = LOGO_ASSETS_DIR / logo_filename
            if logo_path.exists():
                source = QPixmap(str(logo_path))
                if not source.isNull():
                    normalized = BubbleWidget._normalized_logo_pixmap(source)
                    icon = QIcon(normalized)
                    PROVIDER_ICON_CACHE[provider_name] = icon
                    return icon

        icon = BubbleWidget._fallback_provider_icon(provider_name)
        PROVIDER_ICON_CACHE[provider_name] = icon
        return icon

    @staticmethod
    def _normalized_logo_pixmap(source: QPixmap) -> QPixmap:
        pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        scaled = source.scaled(
            ICON_SIZE,
            ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        x = (ICON_SIZE - scaled.width()) // 2
        y = (ICON_SIZE - scaled.height()) // 2

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return pixmap

    @staticmethod
    def _fallback_provider_icon(provider_name: str) -> QIcon:
        pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = pixmap.rect().adjusted(1, 1, -1, -1)

        if provider_name == "codex":
            fill_brush = QBrush(QColor("#10a37f"))
            border = QColor("#6de8cb")
            label = "O"
        elif provider_name == "gemini":
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor("#1a73e8"))
            gradient.setColorAt(1.0, QColor("#9b63ff"))
            fill_brush = QBrush(gradient)
            border = QColor("#bfd3ff")
            label = "G"
        else:
            fill_brush = QBrush(QColor("#1d1d1d"))
            border = QColor("#a0a0a0")
            label = BubbleWidget._provider_company(provider_name)[:1].upper()

        painter.setPen(QPen(border, 1))
        painter.setBrush(fill_brush)
        painter.drawRoundedRect(rect, 4, 4)

        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f5f5f5"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()

        return QIcon(pixmap)

    def get_model_id(self) -> Optional[str]:
        return self.model_selector.current_model_id()

    def set_model_id(self, model_id: str):
        self.model_selector.set_model_id(model_id)

    def show_output(self, visible: bool = True):
        self._output_frame.setVisible(visible)
