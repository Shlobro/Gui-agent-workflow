"""Main application window."""

import json
import os

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QFileDialog,
    QStatusBar,
    QToolBar,
    QWidget,
)

from .canvas import WorkflowCanvas
from .llm_node import LLMNode
from .file_op_node import FileOpNode
from .project_chooser import ProjectChooserDialog, add_to_recent
from .properties_panel import PropertiesPanel


class MainWindow(QMainWindow):
    def __init__(self, project_folder: str | None = None):
        super().__init__()
        self.setWindowTitle("LLM Workflow")
        self.resize(1280, 800)
        self._setup_style()

        self.canvas = WorkflowCanvas()
        self._panel = PropertiesPanel(parent=self.canvas)
        self._panel.raise_()
        self.setCentralWidget(self.canvas)

        # Keep the panel pinned to the top-right corner of the canvas viewport.
        self.canvas.installEventFilter(self)
        # Reposition whenever the panel animates (width changes).
        self._panel._anim.valueChanged.connect(lambda _: self._reposition_panel())

        self.canvas.status_update.connect(self._on_status)
        self.canvas.selection_changed.connect(self._on_selection_changed)

        # Wire panel signals → canvas undo handlers
        self._panel.title_committed.connect(self._on_panel_title_committed)
        self._panel.model_changed.connect(self._on_panel_model_changed)
        self._panel.prompt_committed.connect(self._on_panel_prompt_committed)
        self._panel.filename_committed.connect(self._on_panel_filename_committed)
        self._panel.op_type_changed.connect(self._on_panel_op_type_changed)

        # Wire canvas output callbacks → panel
        self.canvas.on_output_line = lambda node, line: self._panel.maybe_append_output(node, line)
        self.canvas.on_output_cleared = lambda node: self._panel.maybe_clear_output(node)

        self._run_from_here_action: QAction | None = None  # set in _build_toolbar
        self._open_folder_action: QAction | None = None    # set in _build_menu
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

    def _reposition_panel(self) -> None:
        """Pin the panel to the top-right corner of the canvas viewport.

        Since the panel is absolutely positioned (not in a layout), we drive its
        width directly from maximumWidth so the animation value is respected.
        """
        cw = self.canvas.width()
        ch = self.canvas.height()
        pw = self._panel.maximumWidth()
        self._panel.setGeometry(cw - pw, 0, pw, ch)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.canvas and event.type() == QEvent.Type.Resize:
            self._reposition_panel()
        return super().eventFilter(obj, event)

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

        act("＋ LLM Call", self.canvas.add_llm_node, tip="Add a new LLM call node")
        act("＋ File Op", self.canvas.add_file_op_node, tip="Add a file operation node (set type in the panel)")
        tb.addSeparator()
        act("▶ Run All", self._run_all, shortcut="F5",
            tip="Run all nodes reachable from Start")
        act("▶ Run Selected", self._run_selected_only,
            tip="Run only the selected node(s) without fan-out")
        self._run_from_here_action = act(
            "▶ Run From Here", self._run_from_here,
            tip="Run the selected node and all its descendants",
        )
        self._run_from_here_action.setEnabled(False)
        act("■ Stop", self.canvas.stop_all, tip="Cancel running workers")
        tb.addSeparator()
        act("🗑 Clear", self._clear, tip="Clear the canvas")
        tb.addSeparator()
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo)
        self.canvas._undo_stack.canUndoChanged.connect(undo_action.setEnabled)
        self.canvas._undo_stack.undoTextChanged.connect(
            lambda text: undo_action.setText(f"Undo {text}" if text else "Undo")
        )
        undo_action.setEnabled(self.canvas._undo_stack.canUndo())
        tb.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._redo)
        self.canvas._undo_stack.canRedoChanged.connect(redo_action.setEnabled)
        self.canvas._undo_stack.redoTextChanged.connect(
            lambda text: redo_action.setText(f"Redo {text}" if text else "Redo")
        )
        redo_action.setEnabled(self.canvas._undo_stack.canRedo())
        tb.addAction(redo_action)

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

    def _undo(self):
        self._panel.commit_pending_edits()
        self.canvas._undo_stack.undo()

    def _redo(self):
        self._panel.commit_pending_edits()
        self.canvas._undo_stack.redo()

    def _on_status(self, msg: str):
        self._status_bar.showMessage(msg)

    def _on_selection_changed(self):
        selected = [
            i for i in self.canvas._scene.selectedItems()
            if isinstance(i, (LLMNode, FileOpNode)) and not getattr(i, 'is_start', False)
        ]
        if len(selected) == 1:
            self._panel.show_for_node(selected[0])
        else:
            self._panel.hide_panel()
        if self._run_from_here_action is not None:
            self._run_from_here_action.setEnabled(len(selected) == 1)

    # ------------------------------------------------------------------
    # Panel signal handlers
    # ------------------------------------------------------------------

    def _on_panel_title_committed(self, node_id: str, old_title: str, new_title: str):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_title_editing_finished(node_id, new_title)

    def _on_panel_model_changed(self, node_id: str, old_model_id: str, new_model_id: str):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_model_changed(node_id, old_model_id, new_model_id)

    def _on_panel_prompt_committed(self, node_id: str, text: str):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, LLMNode):
            node.prompt_text = text

    def _on_panel_filename_committed(self, node_id: str, text: str):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, FileOpNode):
            node.filename = text

    def _on_panel_op_type_changed(self, node_id: str, old_type: str, new_type: str):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_op_type_changed(node_id, old_type, new_type)

    # ------------------------------------------------------------------

    def _run_all(self):
        self._panel.commit_pending_edits()
        self.canvas.run_all()

    def _run_selected_only(self):
        self._panel.commit_pending_edits()
        self.canvas.run_selected_only()

    def _run_from_here(self):
        self._panel.commit_pending_edits()
        self.canvas.run_from_here()

    def _save(self):
        self._panel.commit_pending_edits()
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
            # Commit and detach panel before destructive canvas mutations.
            self._panel.hide_panel()
            self.canvas.load_workflow_data(data)
            self._status_bar.showMessage(f"Loaded from {path}")
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _clear(self):
        reply = QMessageBox.question(
            self, "Clear Canvas",
            "Remove all nodes and connections?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Commit and detach panel before destructive canvas mutations.
            self._panel.hide_panel()
            self.canvas.clear_canvas()
            self._status_bar.showMessage("Canvas cleared.")
