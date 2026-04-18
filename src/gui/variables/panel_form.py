"""Variable-node properties form."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .variable_node import VARIABLE_TYPE_OPTIONS


class _VariableForm(QWidget):
    variable_type_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("VARIABLE")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)
        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        variable_name_label = QLabel("Variable Name")
        layout.addWidget(variable_name_label)
        self.variable_name_edit = QLineEdit()
        self.variable_name_edit.setPlaceholderText("e.g. customer_name")
        layout.addWidget(self.variable_name_edit)

        variable_type_label = QLabel("Variable Type")
        layout.addWidget(variable_type_label)
        self.variable_type_combo = QComboBox()
        for key, label in VARIABLE_TYPE_OPTIONS:
            self.variable_type_combo.addItem(label, userData=key)
        layout.addWidget(self.variable_type_combo)

        value_label = QLabel("Value")
        layout.addWidget(value_label)
        self.value_edit = QPlainTextEdit()
        self.value_edit.setPlaceholderText("Enter the value that downstream prompts should use.")
        self.value_edit.setMinimumHeight(100)
        self.value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.value_edit, stretch=1)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warning_label")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Output")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(60)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        self._current_variable_type = VARIABLE_TYPE_OPTIONS[0][0]
        self.variable_type_combo.currentIndexChanged.connect(self._on_type_changed)

    def _on_type_changed(self, index: int) -> None:
        new_type = self.variable_type_combo.itemData(index)
        if new_type and new_type != self._current_variable_type:
            old_type = self._current_variable_type
            self._current_variable_type = new_type
            self.variable_type_changed.emit(old_type, new_type)

    def set_variable_type(self, variable_type: str) -> None:
        self.variable_type_combo.blockSignals(True)
        for index in range(self.variable_type_combo.count()):
            if self.variable_type_combo.itemData(index) == variable_type:
                self.variable_type_combo.setCurrentIndex(index)
                break
        self._current_variable_type = self.variable_type_combo.currentData() or VARIABLE_TYPE_OPTIONS[0][0]
        self.variable_type_combo.blockSignals(False)

    def set_warning_text(self, text: str) -> None:
        normalized = (text or "").strip()
        self.warning_label.setText(normalized)
        self.warning_label.setVisible(bool(normalized))

    def show_output(self, visible: bool) -> None:
        self._output_frame.setVisible(visible)
