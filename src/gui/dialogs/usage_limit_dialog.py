"""Dialog shown when an LLM CLI reports a usage or rate limit error."""

from PySide6.QtCore import QDateTime, QTime, Qt
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDial,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
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
QPushButton#schedule_resume_btn {
    background: #375a26;
    border-color: #75b947;
    color: #e8e8e8;
}
QPushButton#schedule_resume_btn:hover { background: #426e2f; }
QCalendarWidget QWidget {
    background: #252525;
    color: #e8e8e8;
}
QCalendarWidget QToolButton {
    color: #e8e8e8;
    background: #333;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
}
QCalendarWidget QMenu {
    background: #2a2a2a;
    color: #e8e8e8;
}
QCalendarWidget QAbstractItemView:enabled {
    background: #1f1f1f;
    color: #e8e8e8;
    selection-background-color: #2f5f2f;
    selection-color: #ffffff;
}
QDial, QLabel#time_value {
    background: #2a2a2a;
    color: #e8e8e8;
    border: 1px solid #555;
    border-radius: 4px;
}
QLabel#time_value {
    padding: 4px 8px;
    font-size: 16px;
    font-weight: bold;
    min-width: 64px;
    qproperty-alignment: AlignCenter;
}
QLabel#selection_preview {
    color: #8fd0a6;
    background: #1f2a23;
    border: 1px solid #355243;
    border-radius: 4px;
    padding: 6px 8px;
}
"""


class UsageLimitDialog(QDialog):
    """Modal dialog presented when a usage or rate limit error is detected.

    The dialog lets the user choose between selecting a different model on the
    failed node (``CHANGE_MODEL``), scheduling an automatic resume
    (``SCHEDULE_RESUME``), or leaving the workflow stopped (``STOP_WORKFLOW``).
    """

    CHANGE_MODEL = 0
    STOP_WORKFLOW = 1
    SCHEDULE_RESUME = 2

    def __init__(self, node_title: str, error_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Usage Limit Reached")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(_STYLE)
        self._result_code = self.STOP_WORKFLOW
        self._scheduled_time = QDateTime.currentDateTime().addSecs(30 * 60)

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
            "You can switch the model, schedule a resume, or leave it stopped."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info_label)

        self._schedule_panel = QWidget()
        schedule_layout = QVBoxLayout(self._schedule_panel)
        schedule_layout.setContentsMargins(0, 0, 0, 0)
        schedule_layout.setSpacing(10)

        self._calendar = QCalendarWidget()
        self._calendar.setSelectedDate(self._scheduled_time.date())
        schedule_layout.addWidget(self._calendar)

        time_label = QLabel("Time (24h)")
        time_label.setStyleSheet("color: #d6d6d6;")
        schedule_layout.addWidget(time_label)

        self._hour_dial = QDial()
        self._hour_dial.setRange(0, 23)
        self._hour_dial.setWrapping(True)
        self._hour_dial.setNotchesVisible(True)
        self._hour_dial.setValue(self._scheduled_time.time().hour())
        self._hour_dial.setFixedSize(86, 86)
        self._hour_value = QLabel("00")
        self._hour_value.setObjectName("time_value")
        hour_col = QVBoxLayout()
        hour_col.setSpacing(4)
        hour_col.addWidget(QLabel("Hour"))
        hour_col.addWidget(self._hour_dial, alignment=Qt.AlignmentFlag.AlignHCenter)
        hour_col.addWidget(self._hour_value, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._minute_dial = QDial()
        self._minute_dial.setRange(0, 59)
        self._minute_dial.setWrapping(True)
        self._minute_dial.setNotchesVisible(True)
        self._minute_dial.setValue(self._scheduled_time.time().minute())
        self._minute_dial.setFixedSize(86, 86)
        self._minute_value = QLabel("00")
        self._minute_value.setObjectName("time_value")
        minute_col = QVBoxLayout()
        minute_col.setSpacing(4)
        minute_col.addWidget(QLabel("Minute"))
        minute_col.addWidget(self._minute_dial, alignment=Qt.AlignmentFlag.AlignHCenter)
        minute_col.addWidget(self._minute_value, alignment=Qt.AlignmentFlag.AlignHCenter)

        time_row = QHBoxLayout()
        time_row.setSpacing(24)
        time_row.addStretch(1)
        time_row.addLayout(hour_col)
        time_row.addLayout(minute_col)
        time_row.addStretch(1)
        schedule_layout.addLayout(time_row)

        self._selection_preview = QLabel("")
        self._selection_preview.setObjectName("selection_preview")
        schedule_layout.addWidget(self._selection_preview)
        schedule_layout.addWidget(QLabel("Local timezone"))

        layout.addWidget(self._schedule_panel)
        self._schedule_panel.setVisible(False)

        buttons = QDialogButtonBox(Qt.Orientation.Horizontal)
        self._schedule_btn = QPushButton("Schedule Resume")
        self._schedule_btn.setObjectName("schedule_resume_btn")
        change_btn = QPushButton("Change Model")
        change_btn.setObjectName("change_model_btn")
        stop_btn = QPushButton("Stop Workflow")
        buttons.addButton(self._schedule_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(change_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(stop_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)
        self._schedule_controls_visible = False

        self._calendar.selectionChanged.connect(self._update_selected_preview)
        self._hour_dial.valueChanged.connect(self._update_selected_preview)
        self._minute_dial.valueChanged.connect(self._update_selected_preview)
        self._update_selected_preview()

        self._schedule_btn.clicked.connect(self._on_schedule_resume)
        change_btn.clicked.connect(self._on_change_model)
        stop_btn.clicked.connect(self._on_stop_workflow)

    def _selected_datetime(self) -> QDateTime:
        selected_date = self._calendar.selectedDate()
        selected_time = QTime(self._hour_dial.value(), self._minute_dial.value())
        return QDateTime(selected_date, selected_time)

    def _update_selected_preview(self):
        self._hour_value.setText(f"{self._hour_dial.value():02d}")
        self._minute_value.setText(f"{self._minute_dial.value():02d}")
        selected = self._selected_datetime()
        self._selection_preview.setText(
            f"Selected schedule: {selected.toString('yyyy-MM-dd HH:mm')}"
        )

    def _on_schedule_resume(self):
        if not self._schedule_controls_visible:
            self._schedule_controls_visible = True
            self._schedule_panel.setVisible(True)
            self._schedule_btn.setText("Confirm Schedule")
            self.adjustSize()
            return

        now = QDateTime.currentDateTime()
        selected = self._selected_datetime()
        if selected <= now:
            QMessageBox.warning(
                self,
                "Schedule Resume",
                "Pick a future date and time.",
            )
            return
        self._scheduled_time = selected
        self._result_code = self.SCHEDULE_RESUME
        self.accept()

    def _on_change_model(self):
        self._result_code = self.CHANGE_MODEL
        self.accept()

    def _on_stop_workflow(self):
        self._result_code = self.STOP_WORKFLOW
        self.reject()

    def result_code(self) -> int:
        """Return ``CHANGE_MODEL``, ``SCHEDULE_RESUME``, or ``STOP_WORKFLOW``."""
        return self._result_code

    def scheduled_time(self) -> QDateTime:
        """Return the chosen local datetime for auto-resume."""
        return self._scheduled_time
