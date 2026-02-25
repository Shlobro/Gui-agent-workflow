"""Dialog shown when a new connection is created between two bubbles."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QFrame,
)
from PySide6.QtCore import Qt


class ConnectionDialog(QDialog):
    def __init__(self, source_name: str, target_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Connection")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel(f"<b>{source_name}</b>  →  <b>{target_name}</b>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Inject checkbox
        self.inject_checkbox = QCheckBox(
            f"Inject output of \"{source_name}\" into the next prompt"
        )
        self.inject_checkbox.setChecked(True)
        layout.addWidget(self.inject_checkbox)

        # Hint
        self.hint_label = QLabel(
            f"Use <code>{{{{prev_output}}}}</code> anywhere in \"{target_name}\"'s prompt "
            "to insert the output at that position.\n"
            "If the placeholder is absent, the output is appended at the end."
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.hint_label)

        self.inject_checkbox.toggled.connect(self.hint_label.setVisible)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    @property
    def inject_output(self) -> bool:
        return self.inject_checkbox.isChecked()
