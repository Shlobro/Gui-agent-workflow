"""Main application window."""

import json
import os

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
)

from .canvas import WorkflowCanvas
from .conditional_node import ConditionalNode
from .file_op_node import AttentionNode, FileOpNode
from .git_action_node import GitActionNode
from .llm_node import LLMNode
from .loop_node import LoopNode
from .project_chooser import ProjectChooserDialog, add_to_recent
from .properties_panel import DEFAULT_PANEL_WIDTH, DEFAULT_TEXT_ZOOM, PropertiesPanel

_PANEL_WIDTH_KEY = "properties_panel/width"
_PANEL_TEXT_ZOOM_KEY = "properties_panel/text_zoom"


class MainWindow(QMainWindow):
    def __init__(self, project_folder: str | None = None):
        super().__init__()
        self.setWindowTitle("LLM Workflow")
        self.resize(1280, 800)
        self._setup_style()

        self._settings = QSettings()
        self._panel_width = self._load_int_setting(_PANEL_WIDTH_KEY, DEFAULT_PANEL_WIDTH)
        self._panel_zoom = self._load_int_setting(_PANEL_TEXT_ZOOM_KEY, DEFAULT_TEXT_ZOOM)
        self._restoring_panel_width = False

        self.canvas = WorkflowCanvas()
        self._panel = PropertiesPanel()
        self._panel.set_preferred_width(self._panel_width)
        self._panel.set_text_zoom(self._panel_zoom)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        self._splitter.addWidget(self.canvas)
        self._splitter.addWidget(self._panel)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self.setCentralWidget(self._splitter)
        self._panel.hide()

        self.canvas.status_update.connect(self._on_status)
        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.usage_limit_hit.connect(self._on_usage_limit_hit)

        self._panel.title_committed.connect(self._on_panel_title_committed)
        self._panel.model_changed.connect(self._on_panel_model_changed)
        self._panel.prompt_committed.connect(self._on_panel_prompt_committed)
        self._panel.filename_committed.connect(self._on_panel_filename_committed)
        self._panel.attention_message_committed.connect(self._on_panel_attention_message_committed)
        self._panel.op_type_changed.connect(self._on_panel_op_type_changed)
        self._panel.condition_type_changed.connect(self._on_panel_condition_type_changed)
        self._panel.loop_count_changed.connect(self._on_panel_loop_count_changed)
        self._panel.git_action_changed.connect(
            lambda nid, old, new: self.canvas._on_git_action_changed(nid, old, new)
        )
        self._panel.text_zoom_changed.connect(self._on_panel_text_zoom_changed)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        self.canvas.on_output_line = lambda node, line: self._panel.maybe_append_output(node, line)
        self.canvas.on_output_cleared = lambda node: self._panel.maybe_clear_output(node)

        self._run_from_here_action: QAction | None = None
        self._open_folder_action: QAction | None = None
        self._build_menu()
        self._build_toolbar()
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self.canvas.run_state_changed.connect(self._on_run_state_changed)

        if project_folder:
            self._apply_project_folder(project_folder)
        else:
            self._status_bar.showMessage("Ready. No project folder selected.")

    def _load_int_setting(self, key: str, default: int) -> int:
        value = self._settings.value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _save_panel_preferences(self) -> None:
        self._settings.setValue(_PANEL_WIDTH_KEY, self._panel_width)
        self._settings.setValue(_PANEL_TEXT_ZOOM_KEY, self._panel_zoom)
        self._settings.sync()

    def _show_panel(self) -> None:
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        if self._panel.isHidden():
            self._panel.show()
        QTimer.singleShot(0, lambda: self._restore_panel_width_and_recenter(center))

    def _hide_panel(self, preserve_center: bool = True) -> None:
        if self._panel.isVisible():
            self._panel_width = self._panel.preferred_width()
            self._save_panel_preferences()
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        self._panel.hide_panel()
        self._panel.hide()
        self._restoring_panel_width = True
        try:
            self._splitter.setSizes([1, 0])
        finally:
            self._restoring_panel_width = False
        if preserve_center:
            QTimer.singleShot(0, lambda: self.canvas.centerOn(center))

    def _restore_panel_width(self) -> None:
        if self._panel.isHidden():
            return
        total_width = max(1, self._splitter.width())
        width = min(self._panel.preferred_width(), max(1, total_width - 220))
        self._restoring_panel_width = True
        try:
            self._splitter.setSizes([max(1, total_width - width), width])
        finally:
            self._restoring_panel_width = False

    def _restore_panel_width_and_recenter(self, center) -> None:
        self._restore_panel_width()
        self.canvas.centerOn(center)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._restoring_panel_width or not self._panel.isVisible():
            return
        width = self._panel.width()
        if width > 0:
            self._panel.set_preferred_width(width)
            self._panel_width = self._panel.preferred_width()
            self._save_panel_preferences()

    def _on_panel_text_zoom_changed(self, zoom: int) -> None:
        self._panel_zoom = zoom
        self._save_panel_preferences()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._panel.isVisible():
            center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            QTimer.singleShot(0, lambda: self._restore_panel_width_and_recenter(center))

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
            QSplitter::handle { background: #252525; }
            QSplitter::handle:hover { background: #3a8ef5; }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 2px 1px 2px 1px;
            }
            QScrollBar::handle:vertical {
                background: #4b4f58;
                border-radius: 6px;
                min-height: 34px;
            }
            QScrollBar::handle:vertical:hover { background: #637997; }
            QScrollBar::handle:vertical:pressed { background: #7b9bc1; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QScrollBar:horizontal {
                background: transparent;
                height: 12px;
                margin: 1px 2px 1px 2px;
            }
            QScrollBar::handle:horizontal {
                background: #4b4f58;
                border-radius: 6px;
                min-width: 34px;
            }
            QScrollBar::handle:horizontal:hover { background: #637997; }
            QScrollBar::handle:horizontal:pressed { background: #7b9bc1; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
        """)

    def _build_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        file_menu.setToolTipsVisible(True)

        open_action = QAction("Open Project Folder", self)
        open_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_action.setToolTip("Choose the folder LLM calls will run in")
        open_action.triggered.connect(self._open_folder)
        file_menu.addAction(open_action)
        self._open_folder_action = open_action

        file_menu.addSeparator()

        save_action = QAction("Save Workflow", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save)
        file_menu.addAction(save_action)

        load_action = QAction("Load Workflow", self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self._load)
        file_menu.addAction(load_action)

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(label, slot, shortcut=None, tip=None):
            action = QAction(label, self)
            action.triggered.connect(slot)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            if tip:
                action.setToolTip(tip)
            tb.addAction(action)
            return action

        act("Add LLM Call", self.canvas.add_llm_node, tip="Add a new LLM call node")
        act("Add File Op", self.canvas.add_file_op_node, tip="Add a file operation node (set type in the panel)")
        act("Add Conditional", self.canvas.add_conditional_node, tip="Add a conditional node that routes execution to true/false branches")
        act("Add Attention", self.canvas.add_attention_node, tip="Add a node that alerts the user and asks whether to continue")
        act("Add Loop", self.canvas.add_loop_node, tip="Add a loop node that repeats N times")
        act("Add Git", self.canvas.add_git_action_node, tip="Add a git action node (add / commit / push)")
        tb.addSeparator()
        act("Run All", self._run_all, shortcut="F5", tip="Run all nodes reachable from Start")
        act("Run Selected", self._run_selected_only, tip="Run only the selected node(s) without fan-out")
        self._run_from_here_action = act(
            "Run From Here",
            self._run_from_here,
            tip="Run the selected node and all its descendants",
        )
        self._run_from_here_action.setEnabled(False)
        act("Stop", self.canvas.stop_all, tip="Cancel running workers")
        tb.addSeparator()
        act("Clear", self._clear, tip="Clear the canvas")
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

    def _apply_project_folder(self, folder: str) -> None:
        folder = os.path.normpath(folder)
        self.canvas.set_working_directory(folder)
        add_to_recent(folder)
        name = os.path.basename(folder)
        self.setWindowTitle(f"LLM Workflow - {name}")
        self._status_bar.showMessage(f"Project folder: {folder}")

    def _open_folder(self):
        dlg = ProjectChooserDialog(self)
        if dlg.exec() == ProjectChooserDialog.DialogCode.Accepted and dlg.chosen_folder:
            self._apply_project_folder(dlg.chosen_folder)

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

    def _on_usage_limit_hit(self, node_id: str, error_text: str) -> None:
        from .dialogs.usage_limit_dialog import UsageLimitDialog

        node = self.canvas._nodes.get(node_id)
        node_title = getattr(node, "title", node_id) if node else node_id
        dlg = UsageLimitDialog(node_title=node_title, error_text=error_text, parent=self)
        dlg.exec()
        if dlg.result_code() == UsageLimitDialog.CHANGE_MODEL and node is not None:
            self.canvas._scene.clearSelection()
            node.setSelected(True)
            QTimer.singleShot(0, lambda: self.canvas.ensureVisible(node))

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
            item
            for item in self.canvas._scene.selectedItems()
            if isinstance(item, (LLMNode, AttentionNode, FileOpNode, ConditionalNode, LoopNode, GitActionNode))
            and not getattr(item, "is_start", False)
        ]
        if len(selected) == 1:
            self._panel.show_for_node(selected[0])
            self._show_panel()
        else:
            self._hide_panel()
        if self._run_from_here_action is not None:
            self._run_from_here_action.setEnabled(len(selected) == 1)

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
        if node is not None and isinstance(node, (FileOpNode, ConditionalNode)):
            node.filename = text

    def _on_panel_attention_message_committed(self, node_id: str, text: str):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, AttentionNode):
            node.message_text = text

    def _on_panel_op_type_changed(self, node_id: str, old_type: str, new_type: str):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_op_type_changed(node_id, old_type, new_type)

    def _on_panel_condition_type_changed(self, node_id: str, old_type: str, new_type: str):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_condition_type_changed(node_id, old_type, new_type)

    def _on_panel_loop_count_changed(self, node_id: str, old_count: int, new_count: int):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_loop_count_changed(node_id, old_count, new_count)

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
            with open(path, "w", encoding="utf-8") as file_obj:
                json.dump(data, file_obj, indent=2)
            self._status_bar.showMessage(f"Saved to {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Workflow", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            self._hide_panel(preserve_center=False)
            self.canvas.load_workflow_data(data)
            self._status_bar.showMessage(f"Loaded from {path}")
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _clear(self):
        reply = QMessageBox.question(
            self,
            "Clear Canvas",
            "Remove all nodes and connections?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._hide_panel(preserve_center=False)
            self.canvas.clear_canvas()
            self._status_bar.showMessage("Canvas cleared.")
