"""Checked multi-select dropdown widget for properties-panel forms."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class _CheckedListWidget(QListWidget):
    """Popup list that stays open while users toggle multiple items."""

    def __init__(self, on_focus_lost, parent=None):
        super().__init__(parent)
        self._on_focus_lost = on_focus_lost

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._on_focus_lost:
            self._on_focus_lost()


class CheckedDropdown(QWidget):
    """Compact dropdown that shows a checkable popup list."""

    selection_changed = Signal(tuple)

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
        QListWidget::item:hover {
            background: #324056;
        }
        QScrollBar:vertical {
            background: #20242b;
            width: 18px;
            padding: 2px;
            border-radius: 9px;
        }
        QScrollBar::handle:vertical {
            background: #6f8fb3;
            border: 2px solid #20242b;
            border-radius: 7px;
            min-height: 52px;
        }
        QScrollBar::handle:vertical:hover { background: #83a4ca; }
        QScrollBar::handle:vertical:pressed { background: #95b8df; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
            background: transparent;
            width: 0px;
            height: 0px;
        }
    """

    def __init__(self, popup_parent: QWidget, parent=None):
        super().__init__(parent)
        self._popup_parent = popup_parent
        self._placeholder_text = ""
        self._dropdown_height = 0
        self._suppress_emits = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toggle_button = QPushButton()
        self._toggle_button.setCheckable(True)
        self._toggle_button.setMinimumHeight(26)
        self._toggle_button.clicked.connect(self._on_toggle_clicked)
        layout.addWidget(self._toggle_button)

        self._list = _CheckedListWidget(self._close_dropdown, popup_parent)
        self._list.setObjectName("checked_dropdown_popup")
        self._list.setVisible(False)
        self._list.setStyleSheet(self.LIST_STYLESHEET)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.itemPressed.connect(self._toggle_item_pressed)

        self._update_button_label()

    def set_placeholder_text(self, text: str) -> None:
        self._placeholder_text = text or ""
        self._update_button_label()

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        checked = set(self.checked_ids())
        self._suppress_emits = True
        try:
            self._list.clear()
            for value, label in items:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, value)
                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if value in checked else Qt.CheckState.Unchecked
                )
                self._list.addItem(item)
        finally:
            self._suppress_emits = False
        self._update_list_height()
        self._update_button_label()

    def checked_ids(self) -> tuple[str, ...]:
        checked: list[str] = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                value = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if value:
                    checked.append(value)
        return tuple(checked)

    def set_checked_ids(self, checked_ids: Sequence[str]) -> None:
        checked = {str(value).strip() for value in checked_ids if str(value).strip()}
        self._suppress_emits = True
        try:
            for index in range(self._list.count()):
                item = self._list.item(index)
                value = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                item.setCheckState(
                    Qt.CheckState.Checked if value in checked else Qt.CheckState.Unchecked
                )
        finally:
            self._suppress_emits = False
        self._update_button_label()

    def _on_toggle_clicked(self) -> None:
        if self._toggle_button.isChecked():
            self._open_dropdown()
            return
        self._close_dropdown()

    def _toggle_item_pressed(self, item: QListWidgetItem) -> None:
        next_state = (
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        item.setCheckState(next_state)

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        self._update_button_label()
        if not self._suppress_emits:
            self.selection_changed.emit(self.checked_ids())

    def _update_button_label(self) -> None:
        checked_labels: list[str] = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                checked_labels.append(item.text())
        if checked_labels:
            self._toggle_button.setText(", ".join(checked_labels))
            return
        self._toggle_button.setText(self._placeholder_text)

    def _update_list_height(self) -> None:
        if self._list.count() == 0:
            self._dropdown_height = 0
            return
        visible_rows = min(self._list.count(), 10)
        row_height = self._list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 24
        frame = self._list.frameWidth() * 2
        self._dropdown_height = frame + (visible_rows * row_height) + 2

    def _open_dropdown(self) -> None:
        if self._list.count() == 0 or self._dropdown_height <= 0:
            self._toggle_button.setChecked(False)
            return
        self._ensure_overlay_parent()
        self._position_dropdown()
        self._list.show()
        self._list.raise_()
        self._list.setFocus(Qt.FocusReason.MouseFocusReason)

    def _close_dropdown(self) -> None:
        self._toggle_button.blockSignals(True)
        self._toggle_button.setChecked(False)
        self._toggle_button.blockSignals(False)
        self._list.hide()

    def _ensure_overlay_parent(self) -> None:
        if self._list.parentWidget() is self._popup_parent:
            return
        self._list.setParent(self._popup_parent)
        self._list.setWindowFlags(Qt.WindowType.Popup)
        self._list.resize(self.width(), self._dropdown_height)

    def _position_dropdown(self) -> None:
        self._list.resize(max(self.width(), 220), self._dropdown_height)
        top_left = self.mapToGlobal(self.rect().bottomLeft())
        parent_origin = self._popup_parent.mapToGlobal(self._popup_parent.rect().topLeft())
        local_pos = top_left - parent_origin
        self._list.move(local_pos)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._list.isVisible():
            self._position_dropdown()
