"""Dialog shown when an LLM CLI reports a usage or rate limit error."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

_STYLE = """
QDialog {
    background: #1e1e1e;
    color: #e8e8e8;
}
QLabel {
    background: transparent;
    color: #e8e8e8;
}
QLabel#error_text {
    color: #cc8888;
    background: #2a2020;
    border: 1px solid #554444;
    border-radius: 4px;
    padding: 6px;
    font-family: monospace;
}
QPushButton {
    background: #333;
    color: #e8e8e8;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 18px;
    min-width: 110px;
}
QPushButton:hover { background: #444; }
QPushButton:pressed { background: #222; }
QPushButton#change_model_btn {
    background: #1a4a8a;
    border-color: #3a8ef5;
    color: #e8e8e8;
}
QPushButton#change_model_btn:hover { background: #265299; }
"""


class UsageLimitDialog(QDialog):
    """Modal dialog presented when a usage or rate limit error is detected.

    The dialog lets the user choose between selecting a different model on the
    failed node (``CHANGE_MODEL``) or leaving the workflow stopped
    (``STOP_WORKFLOW``).
    """

    CHANGE_MODEL = 0
    STOP_WORKFLOW = 1

    def __init__(self, node_title: str, error_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Usage Limit Reached")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(_STYLE)
        self._result_code = self.STOP_WORKFLOW

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel("Usage limit reached")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e8a840;")
        layout.addWidget(title_label)

        node_label = QLabel(f"Node: <b>{node_title}</b>")
        node_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(node_label)

        truncated = error_text.strip()[:300]
        if len(error_text.strip()) > 300:
            truncated += "…"
        error_label = QLabel(truncated)
        error_label.setObjectName("error_text")
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        info_label = QLabel(
            "The workflow has been stopped.\n"
            "You can switch the model on this node and re-run, or leave it stopped."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(Qt.Orientation.Horizontal)
        change_btn = QPushButton("Change Model")
        change_btn.setObjectName("change_model_btn")
        stop_btn = QPushButton("Stop Workflow")
        buttons.addButton(change_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(stop_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

        change_btn.clicked.connect(self._on_change_model)
        stop_btn.clicked.connect(self._on_stop_workflow)

    def _on_change_model(self):
        self._result_code = self.CHANGE_MODEL
        self.accept()

    def _on_stop_workflow(self):
        self._result_code = self.STOP_WORKFLOW
        self.reject()

    def result_code(self) -> int:
        """Return ``CHANGE_MODEL`` or ``STOP_WORKFLOW`` depending on user choice."""
        return self._result_code
