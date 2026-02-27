"""Main application window."""

import json
import os

from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QFileDialog,
    QMessageBox,
)

from .canvas import WorkflowCanvas
from .bubble_node import BubbleNode
from .project_chooser import ProjectChooserDialog, add_to_recent


class MainWindow(QMainWindow):
    def __init__(self, project_folder: str | None = None):
        super().__init__()
        self.setWindowTitle("LLM Workflow")
        self.resize(1280, 800)
        self._setup_style()

        self.canvas = WorkflowCanvas()
        self.setCentralWidget(self.canvas)
        self.canvas.status_update.connect(self._on_status)
        self.canvas.selection_changed.connect(self._on_selection_changed)

        self._run_from_here_action: QAction = None  # set in _build_toolbar
        self._open_folder_action: QAction = None    # set in _build_menu
        self._build_menu()
        self._build_toolbar()
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self.canvas.run_state_changed.connect(self._on_run_state_changed)

        if project_folder:
            self._apply_project_folder(project_folder)
        else:
            self._status_bar.showMessage("Ready. No project folder selected.")

    # ------------------------------------------------------------------

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1a1a1a; color: #e8e8e8; }
            QMenuBar {
                background: #252525; color: #e8e8e8;
                border-bottom: 1px solid #333;
            }
            QMenuBar::item:selected { background: #3a3a3a; }
            QMenu {
                background: #252525; color: #e8e8e8;
                border: 1px solid #444;
            }
            QMenu::item:selected { background: #1e4d7a; }
            QMenu::separator { height: 1px; background: #444; margin: 3px 0; }
            QToolBar { background: #252525; border-bottom: 1px solid #333; spacing: 6px; padding: 4px; }
            QToolButton {
                background: #333; color: #e8e8e8; border: 1px solid #444;
                border-radius: 4px; padding: 4px 10px;
            }
            QToolButton:hover { background: #444; }
            QToolButton:pressed { background: #222; }
            QStatusBar { background: #252525; color: #aaaaaa; }
        """)

    def _build_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        file_menu.setToolTipsVisible(True)

        open_action = QAction("Open Project Folder…", self)
        open_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_action.setToolTip("Choose the folder LLM calls will run in")
        open_action.triggered.connect(self._open_folder)
        file_menu.addAction(open_action)
        self._open_folder_action = open_action

        file_menu.addSeparator()

        save_action = QAction("Save Workflow…", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save)
        file_menu.addAction(save_action)

        load_action = QAction("Load Workflow…", self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self._load)
        file_menu.addAction(load_action)

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
        act("▶ Run All", self.canvas.run_all, shortcut="F5",
            tip="Run all nodes reachable from Start")
        act("▶ Run Selected", self.canvas.run_selected_only,
            tip="Run only the selected node(s) without fan-out")
        self._run_from_here_action = act(
            "▶ Run From Here", self.canvas.run_from_here,
            tip="Run the selected node and all its descendants",
        )
        self._run_from_here_action.setEnabled(False)
        act("■ Stop", self.canvas.stop_all, tip="Cancel running workers")
        tb.addSeparator()
        act("🗑 Clear", self._clear, tip="Clear the canvas")

    # ------------------------------------------------------------------

    def _apply_project_folder(self, folder: str) -> None:
        folder = os.path.normpath(folder)
        self.canvas.set_working_directory(folder)
        add_to_recent(folder)
        name = os.path.basename(folder)
        self.setWindowTitle(f"LLM Workflow — {name}")
        self._status_bar.showMessage(f"Project folder: {folder}")

    def _open_folder(self):
        dlg = ProjectChooserDialog(self)
        if dlg.exec() == ProjectChooserDialog.DialogCode.Accepted and dlg.chosen_folder:
            self._apply_project_folder(dlg.chosen_folder)

    # ------------------------------------------------------------------

    def _on_run_state_changed(self, running: bool) -> None:
        if self._open_folder_action is None:
            return
        self._open_folder_action.setEnabled(not running)
        if running:
            self._open_folder_action.setToolTip(
                "Cannot open a project folder during an active workflow"
            )
        else:
            self._open_folder_action.setToolTip(
                "Choose the folder LLM calls will run in"
            )

    def _on_status(self, msg: str):
        self._status_bar.showMessage(msg)

    def _on_selection_changed(self):
        if self._run_from_here_action is None:
            return
        selected_bubbles = [
            i for i in self.canvas._scene.selectedItems()
            if isinstance(i, BubbleNode) and not getattr(i, 'is_start', False)
        ]
        self._run_from_here_action.setEnabled(len(selected_bubbles) == 1)

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
