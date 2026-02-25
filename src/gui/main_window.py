"""Main application window."""

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QFileDialog,
    QMessageBox, QWidget,
)

from .canvas import WorkflowCanvas


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLM Workflow")
        self.resize(1280, 800)
        self._setup_style()

        self.canvas = WorkflowCanvas()
        self.setCentralWidget(self.canvas)
        self.canvas.status_update.connect(self._on_status)

        self._build_toolbar()
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready.")

    # ------------------------------------------------------------------

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1a1a1a; color: #e8e8e8; }
            QToolBar { background: #252525; border-bottom: 1px solid #333; spacing: 6px; padding: 4px; }
            QToolButton {
                background: #333; color: #e8e8e8; border: 1px solid #444;
                border-radius: 4px; padding: 4px 10px;
            }
            QToolButton:hover { background: #444; }
            QToolButton:pressed { background: #222; }
            QStatusBar { background: #252525; color: #aaaaaa; }
        """)

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(label, slot, shortcut=None, tip=None):
            a = QAction(label, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setToolTip(tip)
            tb.addAction(a)
            return a

        act("＋ Add Bubble", self.canvas.add_bubble, tip="Add a new bubble node")
        tb.addSeparator()
        act("▶ Run All", self.canvas.run_all, shortcut="F5", tip="Run the entire workflow")
        act("▶ Run Selected", self.canvas.run_from_selected, tip="Run from the selected bubble")
        act("■ Stop", self.canvas.stop_all, tip="Cancel running workers")
        tb.addSeparator()
        act("💾 Save", self._save, shortcut="Ctrl+S", tip="Save workflow to JSON")
        act("📂 Load", self._load, shortcut="Ctrl+O", tip="Load workflow from JSON")
        tb.addSeparator()
        act("🗑 Clear", self._clear, tip="Clear the canvas")

    # ------------------------------------------------------------------

    def _on_status(self, msg: str):
        self._status_bar.showMessage(msg)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Workflow", "", "JSON Files (*.json)"
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        data = self.canvas.get_workflow_data()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._status_bar.showMessage(f"Saved to {path}")
        except OSError as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Workflow", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.canvas.load_workflow_data(data)
            self._status_bar.showMessage(f"Loaded from {path}")
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _clear(self):
        reply = QMessageBox.question(
            self, "Clear Canvas",
            "Remove all bubbles and connections?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.clear_canvas()
            self._status_bar.showMessage("Canvas cleared.")
