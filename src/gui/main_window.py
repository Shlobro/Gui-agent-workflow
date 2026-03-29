"""Main application window."""

import json
import os

from PySide6.QtCore import QDateTime, QSettings, Qt, QTimer
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
from .connection_item import ConnectionItem
from .control_flow.join_node import JoinNode
from .dialogs.prompt_injection_dialog import (
    PromptInjectionRunDialog,
    PromptTemplateManagerDialog,
)
from .file_op_node import AttentionNode, FileOpNode
from .git_action_node import GitActionNode
from .llm_node import LLMNode
from .loop_node import LoopNode
from .project_chooser import ProjectChooserDialog, add_to_recent
from .properties_panel import DEFAULT_PANEL_WIDTH, DEFAULT_TEXT_ZOOM, PropertiesPanel
from .script_runner.script_node import SCRIPT_FILE_FILTER, ScriptNode
from src.llm.prompt_injection import (
    PromptInjectionRunOptions,
    PromptInjectionStore,
    normalize_run_options,
    resolve_template_contents,
)

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
        self._prompt_injection_store = PromptInjectionStore()
        self._prompt_injection_config = self._prompt_injection_store.load()
        self._next_run_prompt_injections: PromptInjectionRunOptions | None = None
        self._staged_run_prompt_injections: PromptInjectionRunOptions | None = None
        self._active_run_prompt_injections: PromptInjectionRunOptions | None = None
        self._usage_limit_resume_timer: QTimer | None = None
        self._usage_limit_resume_node_id: str | None = None
        self._usage_limit_resume_target: QDateTime | None = None

        self.canvas = WorkflowCanvas()
        initial_options = self._effective_prompt_injection_options()
        (
            prepend_template_contents,
            append_template_contents,
            one_off_text,
            one_off_placement,
        ) = self._resolve_prompt_injection_payload(initial_options)
        self.canvas.set_prompt_injections(
            prepend_template_contents,
            append_template_contents,
            one_off_text,
            one_off_placement,
        )
        self._panel = PropertiesPanel()
        self._panel.set_preferred_width(self._panel_width)
        self._panel.set_text_zoom(self._panel_zoom)
        self._sync_prompt_preview_context()

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        self._splitter.addWidget(self.canvas)
        self._splitter.addWidget(self._panel)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self.setCentralWidget(self._splitter)
        self._panel.show_overview()

        self.canvas.status_update.connect(self._on_status)
        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.usage_limit_hit.connect(self._on_usage_limit_hit)
        self.canvas._undo_stack.indexChanged.connect(self._on_undo_stack_changed_for_overview)

        self._panel.title_committed.connect(self._on_panel_title_committed)
        self._panel.model_changed.connect(self._on_panel_model_changed)
        self._panel.prompt_committed.connect(self._on_panel_prompt_committed)
        self._panel.filename_committed.connect(self._on_panel_filename_committed)
        self._panel.attention_message_committed.connect(self._on_panel_attention_message_committed)
        self._panel.op_type_changed.connect(self._on_panel_op_type_changed)
        self._panel.condition_type_changed.connect(self._on_panel_condition_type_changed)
        self._panel.loop_count_changed.connect(self._on_panel_loop_count_changed)
        self._panel.join_count_changed.connect(self._on_panel_join_count_changed)
        self._panel.git_action_changed.connect(
            lambda nid, old, new: self.canvas._on_git_action_changed(nid, old, new)
        )
        self._panel.git_details_changed.connect(self._on_panel_git_details_changed)
        self._panel.script_path_committed.connect(self._on_panel_script_path_committed)
        self._panel.script_browse_requested.connect(self._on_panel_script_browse_requested)
        self._panel.script_auto_send_enter_changed.connect(self._on_panel_script_auto_send_enter_changed)
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
        self._refresh_panel_overview()
        QTimer.singleShot(0, self._restore_panel_width)

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

    def _hide_panel(self, preserve_center: bool = True) -> None:
        _ = preserve_center
        self._panel_width = self._panel.preferred_width()
        self._save_panel_preferences()
        self._panel.show_overview()
        self._restore_panel_width()

    def _restore_panel_width(self) -> None:
        total_width = max(1, self._splitter.width())
        width = min(self._panel.preferred_width(), max(1, total_width - 220))
        self._restoring_panel_width = True
        try:
            self._splitter.setSizes([max(1, total_width - width), width])
        finally:
            self._restoring_panel_width = False

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
        QTimer.singleShot(0, self._restore_panel_width)

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
            QScrollBar:horizontal {
                background: #20242b;
                height: 18px;
                padding: 2px;
                border-radius: 9px;
            }
            QScrollBar::handle:horizontal {
                background: #6f8fb3;
                border: 2px solid #20242b;
                border-radius: 7px;
                min-width: 52px;
            }
            QScrollBar::handle:horizontal:hover { background: #83a4ca; }
            QScrollBar::handle:horizontal:pressed { background: #95b8df; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
                background: transparent;
                width: 0px;
                height: 0px;
            }
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

        prompt_menu = menu_bar.addMenu("Prompt")
        prompt_menu.setToolTipsVisible(True)

        templates_action = QAction("Manage Templates", self)
        templates_action.setToolTip("Create and maintain reusable prompt injection templates")
        templates_action.triggered.connect(self._open_prompt_templates)
        prompt_menu.addAction(templates_action)

        next_run_action = QAction("Set Next Run Injection", self)
        next_run_action.setToolTip("Choose templates and one-off context for the next run")
        next_run_action.triggered.connect(self._set_next_run_prompt_injection)
        prompt_menu.addAction(next_run_action)

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
        act("Add Join", self.canvas.add_join_node, tip="Add a barrier node that waits for N arrivals before continuing")
        act("Add Git", self.canvas.add_git_action_node, tip="Add a git action node (add / commit / push)")
        act("Add Script", self.canvas.add_script_node, tip="Add a node that runs a .bat, .cmd, or .ps1 script")
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
        self._refresh_panel_overview()

    def _open_folder(self):
        dlg = ProjectChooserDialog(self)
        if dlg.exec() == ProjectChooserDialog.DialogCode.Accepted and dlg.chosen_folder:
            self._apply_project_folder(dlg.chosen_folder)

    def _on_run_state_changed(self, running: bool) -> None:
        if self._open_folder_action is None:
            return
        if running:
            self._clear_scheduled_usage_limit_resume(
                "Scheduled usage-limit auto-resume canceled because a run started."
            )
        self._open_folder_action.setEnabled(not running)
        if running:
            self._open_folder_action.setToolTip(
                "Cannot open a project folder during an active workflow"
            )
        else:
            self._open_folder_action.setToolTip(
                "Choose the folder LLM calls will run in"
            )
        if running:
            if self._staged_run_prompt_injections is not None:
                self._active_run_prompt_injections = self._staged_run_prompt_injections
                self._staged_run_prompt_injections = None
                self._next_run_prompt_injections = None
                self._sync_prompt_preview_context()
        else:
            self._staged_run_prompt_injections = None
            if self._active_run_prompt_injections is not None:
                self._active_run_prompt_injections = None
                self._sync_prompt_preview_context()

    def _on_usage_limit_hit(self, node_id: str, error_text: str) -> None:
        from .dialogs.usage_limit_dialog import UsageLimitDialog

        node = self.canvas._nodes.get(node_id)
        node_title = getattr(node, "title", node_id) if node else node_id
        dlg = UsageLimitDialog(node_title=node_title, error_text=error_text, parent=self)
        dlg.exec()
        result_code = dlg.result_code()
        if result_code == UsageLimitDialog.CHANGE_MODEL and node is not None:
            self._select_node(node_id)
            return
        if result_code == UsageLimitDialog.SCHEDULE_RESUME:
            self._schedule_usage_limit_resume(node_id, dlg.scheduled_time())

    def _select_node(self, node_id: str) -> bool:
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return False
        self.canvas._scene.clearSelection()
        node.setSelected(True)
        QTimer.singleShot(0, lambda _node=node: self.canvas.ensureVisible(_node))
        return True

    def _schedule_usage_limit_resume(self, node_id: str, target_time: QDateTime) -> None:
        if node_id not in self.canvas._nodes:
            QMessageBox.warning(
                self,
                "Schedule Resume",
                "Cannot schedule auto-resume because the node no longer exists.",
            )
            return
        if not target_time.isValid():
            QMessageBox.warning(self, "Schedule Resume", "Invalid resume time.")
            return
        now = QDateTime.currentDateTime()
        if target_time <= now:
            target_time = now.addSecs(1)
        delay_ms = int(now.msecsTo(target_time))
        max_qtimer_ms = 2_147_483_647
        if delay_ms > max_qtimer_ms:
            QMessageBox.warning(
                self,
                "Schedule Resume",
                "Resume time is too far in the future for a single timer.",
            )
            return

        self._clear_scheduled_usage_limit_resume()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._fire_scheduled_usage_limit_resume)
        timer.start(delay_ms)
        self._usage_limit_resume_timer = timer
        self._usage_limit_resume_node_id = node_id
        self._usage_limit_resume_target = target_time
        node_title = getattr(self.canvas._nodes[node_id], "title", node_id)
        when_text = target_time.toString("yyyy-MM-dd HH:mm")
        self._status_bar.showMessage(
            f'Auto-resume scheduled for "{node_title}" at {when_text}.'
        )

    def _clear_scheduled_usage_limit_resume(self, status_message: str = "") -> None:
        had_schedule = (
            self._usage_limit_resume_timer is not None
            or self._usage_limit_resume_node_id is not None
            or self._usage_limit_resume_target is not None
        )
        if self._usage_limit_resume_timer is not None:
            self._usage_limit_resume_timer.stop()
            self._usage_limit_resume_timer.deleteLater()
        self._usage_limit_resume_timer = None
        self._usage_limit_resume_node_id = None
        self._usage_limit_resume_target = None
        if status_message and had_schedule:
            self._status_bar.showMessage(status_message)

    def _fire_scheduled_usage_limit_resume(self) -> None:
        node_id = self._usage_limit_resume_node_id
        scheduled_for = self._usage_limit_resume_target
        self._clear_scheduled_usage_limit_resume()
        if not node_id:
            return
        if self.canvas._running:
            self._status_bar.showMessage(
                "Skipped scheduled auto-resume because a workflow is already running."
            )
            return
        node = self.canvas._nodes.get(node_id)
        if node is None:
            self._status_bar.showMessage(
                "Scheduled auto-resume canceled because the node was removed."
            )
            return
        when_text = scheduled_for.toString("yyyy-MM-dd HH:mm") if scheduled_for else "scheduled time"
        self._status_bar.showMessage(
            f'Auto-resume triggered for "{node.title}" ({when_text}).'
        )
        self._run_from_specific_node(node_id)

    def _run_from_specific_node(self, node_id: str) -> bool:
        if not self._select_node(node_id):
            return False
        self._run_from_here()
        return True

    def _undo(self):
        self._panel.commit_pending_edits()
        self.canvas._undo_stack.undo()

    def _redo(self):
        self._panel.commit_pending_edits()
        self.canvas._undo_stack.redo()

    def _on_status(self, msg: str):
        self._status_bar.showMessage(msg)

    def _selected_nodes(self) -> list:
        return [
            item
            for item in self.canvas._scene.selectedItems()
            if isinstance(item, (LLMNode, AttentionNode, FileOpNode, ConditionalNode, LoopNode, JoinNode, GitActionNode, ScriptNode))
            and not getattr(item, "is_start", False)
        ]

    def _selected_connections(self) -> list[ConnectionItem]:
        return [
            item
            for item in self.canvas._scene.selectedItems()
            if isinstance(item, ConnectionItem)
        ]

    @staticmethod
    def _connection_endpoint_name(node) -> str:
        if getattr(node, "is_start", False):
            return "Start"
        return getattr(node, "title", getattr(node, "node_id", "(unknown)"))

    def _set_connection_overview(self, conn: ConnectionItem) -> None:
        source_name = self._connection_endpoint_name(conn.source_node)
        target_name = self._connection_endpoint_name(conn.target_node)
        source_id = getattr(conn.source_node, "node_id", "(unknown)")
        target_id = getattr(conn.target_node, "node_id", "(unknown)")
        source_port = getattr(conn, "source_port", "output")
        vertex_count = len(conn.editable_points())
        lines = [
            "Selected Arrow",
            "",
            "Endpoints",
            f"- From: {source_name}",
            f"- To: {target_name}",
            "",
            "Connection Details",
            f"- Source node id: {source_id}",
            f"- Target node id: {target_id}",
            f"- Source port: {source_port}",
            f"- Bend points: {vertex_count}",
            "",
            "Editing",
            "- Double-click line segment: add bend point",
            "- Drag bend handle: move bend point",
            "- Shift+click bend handle: remove bend point",
            "- Delete: delete selected arrow",
            "- Ctrl+Z / Ctrl+Y: undo / redo",
        ]
        self._panel.set_overview_text("\n".join(lines))

    def _on_selection_changed(self):
        selected_nodes = self._selected_nodes()
        selected_connections = self._selected_connections()

        if len(selected_nodes) == 1 and not selected_connections:
            self._panel.show_for_node(selected_nodes[0])
        else:
            self._panel.show_overview()
        if self._run_from_here_action is not None:
            self._run_from_here_action.setEnabled(len(selected_nodes) == 1 and not selected_connections)
        self._refresh_panel_overview()

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
            self.canvas.refresh_node_validation_state()
            self._refresh_panel_overview()

    def _on_panel_filename_committed(self, node_id: str, text: str):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, (FileOpNode, ConditionalNode)):
            node.filename = text
            self.canvas.refresh_node_validation_state()
            self._refresh_panel_overview()

    def _on_panel_attention_message_committed(self, node_id: str, text: str):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, AttentionNode):
            node.message_text = text
            self.canvas.refresh_node_validation_state()
            self._refresh_panel_overview()

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

    def _on_panel_join_count_changed(self, node_id: str, old_count: int, new_count: int):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            return
        self.canvas._on_join_count_changed(node_id, old_count, new_count)

    def _on_panel_git_details_changed(self, node_id: str):
        if node_id in self.canvas._nodes:
            self.canvas.refresh_node_validation_state()
            self._refresh_panel_overview()

    def _on_panel_script_path_committed(self, node_id: str, path: str):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, ScriptNode):
            node.script_path = path
            self.canvas.refresh_node_validation_state()
            self._refresh_panel_overview()

    def _on_panel_script_browse_requested(self, node_id: str):
        node = self.canvas._nodes.get(node_id)
        if node is None or not isinstance(node, ScriptNode):
            return
        working_directory = self.canvas._working_directory
        if not working_directory:
            QMessageBox.warning(
                self,
                "No Project Folder",
                "Open a project folder before selecting a script file.",
            )
            return
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Script",
            working_directory,
            SCRIPT_FILE_FILTER,
        )
        if not selected_path:
            return
        try:
            relative_path = os.path.relpath(selected_path, working_directory)
        except ValueError:
            QMessageBox.warning(self, "Invalid Script", "Selected script must be inside the current project folder.")
            return
        if relative_path.startswith(".."):
            QMessageBox.warning(self, "Invalid Script", "Selected script must be inside the current project folder.")
            return
        node.script_path = relative_path
        self._panel.refresh_if_current(node)
        self.canvas.refresh_node_validation_state()
        self._refresh_panel_overview()

    def _on_panel_script_auto_send_enter_changed(self, node_id: str, checked: bool):
        node = self.canvas._nodes.get(node_id)
        if node is not None and isinstance(node, ScriptNode):
            node.auto_send_enter = bool(checked)
            self._refresh_panel_overview()

    def _run_all(self):
        self._panel.commit_pending_edits()
        self._apply_prompt_injections_for_run()
        self.canvas.run_all()

    def _run_selected_only(self):
        self._panel.commit_pending_edits()
        self._apply_prompt_injections_for_run()
        self.canvas.run_selected_only()

    def _run_from_here(self):
        self._panel.commit_pending_edits()
        self._apply_prompt_injections_for_run()
        self.canvas.run_from_here()

    def _open_prompt_templates(self):
        dialog = PromptTemplateManagerDialog(self._prompt_injection_config, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        new_config = dialog.result_config()
        try:
            self._prompt_injection_store.save(new_config)
        except OSError as exc:
            QMessageBox.critical(self, "Prompt Template Error", str(exc))
            return
        self._prompt_injection_config = self._prompt_injection_store.load()
        self._next_run_prompt_injections = None
        self._sync_prompt_preview_context()
        self._status_bar.showMessage("Prompt templates saved.")

    def _set_next_run_prompt_injection(self):
        seed = self._next_run_prompt_injections
        if seed is None:
            seed = PromptInjectionRunOptions(
                enabled_template_ids=self._prompt_injection_config.default_enabled_template_ids,
                one_off_text="",
            )
        dialog = PromptInjectionRunDialog(
            self._prompt_injection_config,
            current=seed,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._next_run_prompt_injections = dialog.result_options()
        self._sync_prompt_preview_context()
        template_count = len(self._next_run_prompt_injections.enabled_template_ids)
        has_one_off = bool(self._next_run_prompt_injections.one_off_text.strip())
        details = "with one-off context" if has_one_off else "no one-off context"
        one_off_side = self._next_run_prompt_injections.one_off_placement
        self._status_bar.showMessage(
            f"Next run injection set ({template_count} template(s), {details}, one-off {one_off_side})."
        )

    def _apply_prompt_injections_for_run(self):
        options = self._effective_prompt_injection_options()
        (
            prepend_template_contents,
            append_template_contents,
            one_off_text,
            one_off_placement,
        ) = self._resolve_prompt_injection_payload(options)
        self.canvas.set_prompt_injections(
            prepend_template_contents,
            append_template_contents,
            one_off_text,
            one_off_placement,
        )
        self._staged_run_prompt_injections = options
        self._sync_prompt_preview_context()

    def _effective_prompt_injection_options(self) -> PromptInjectionRunOptions:
        return normalize_run_options(
            self._prompt_injection_config,
            self._next_run_prompt_injections,
        )

    def _effective_preview_prompt_injection_options(self) -> PromptInjectionRunOptions:
        if self._active_run_prompt_injections is not None:
            return normalize_run_options(
                self._prompt_injection_config,
                self._active_run_prompt_injections,
            )
        if self._staged_run_prompt_injections is not None:
            return normalize_run_options(
                self._prompt_injection_config,
                self._staged_run_prompt_injections,
            )
        return self._effective_prompt_injection_options()

    def _resolve_prompt_injection_payload(
        self, options: PromptInjectionRunOptions
    ) -> tuple[list[str], list[str], str, str]:
        prepend_template_contents, append_template_contents = resolve_template_contents(
            self._prompt_injection_config,
            options.enabled_template_ids,
        )
        return (
            prepend_template_contents,
            append_template_contents,
            options.one_off_text,
            options.one_off_placement,
        )

    def _sync_prompt_preview_context(self) -> None:
        if not hasattr(self, "_panel"):
            return
        (
            prepend_template_contents,
            append_template_contents,
            one_off_text,
            one_off_placement,
        ) = self._resolve_prompt_injection_payload(self._effective_preview_prompt_injection_options())
        self._panel.set_prompt_injection_preview_context(
            prepend_template_contents,
            append_template_contents,
            one_off_text,
            one_off_placement,
        )
        self._refresh_panel_overview()

    def _on_undo_stack_changed_for_overview(self, _index: int) -> None:
        self._refresh_panel_overview()

    def _refresh_panel_overview(self) -> None:
        if not hasattr(self, "_panel"):
            return
        selected_nodes = self._selected_nodes()
        selected_connections = self._selected_connections()
        if len(selected_connections) == 1 and not selected_nodes:
            self._set_connection_overview(selected_connections[0])
            return
        nodes = list(self.canvas._nodes.values())
        self.canvas.refresh_node_validation_state()

        llm_count = 0
        file_op_count = 0
        conditional_count = 0
        loop_count = 0
        join_count = 0
        attention_count = 0
        git_action_count = 0
        script_count = 0
        invalid_nodes: list[str] = []
        for node in nodes:
            if getattr(node, "is_invalid", False):
                invalid_nodes.append(getattr(node, "title", node.node_id))
            if isinstance(node, AttentionNode):
                attention_count += 1
            elif isinstance(node, ConditionalNode):
                conditional_count += 1
            elif isinstance(node, LoopNode):
                loop_count += 1
            elif isinstance(node, JoinNode):
                join_count += 1
            elif isinstance(node, GitActionNode):
                git_action_count += 1
            elif isinstance(node, ScriptNode):
                script_count += 1
            elif isinstance(node, FileOpNode):
                file_op_count += 1
            elif isinstance(node, LLMNode):
                llm_count += 1

        selected_count = len(selected_nodes)
        selected_connection_count = len(selected_connections)

        options = self._effective_preview_prompt_injection_options()
        prepend_template_contents, append_template_contents, one_off_text, one_off_placement = (
            self._resolve_prompt_injection_payload(options)
        )

        lines = [
            "Workflow Summary",
            f"Working directory: {self.canvas._working_directory or '(not selected)'}",
            f"Connections: {len(self.canvas._connections)}",
            f"Selected nodes: {selected_count}",
            f"Selected arrows: {selected_connection_count}",
            "",
            "Node Counts",
            f"- Total: {len(nodes)}",
            f"- LLM: {llm_count}",
            f"- File Ops: {file_op_count}",
            f"- Conditional: {conditional_count}",
            f"- Attention: {attention_count}",
            f"- Loop: {loop_count}",
            f"- Join: {join_count}",
            f"- Git Action: {git_action_count}",
            f"- Script: {script_count}",
            "",
            f"Invalid Nodes: {len(invalid_nodes)}",
        ]
        if invalid_nodes:
            for title in invalid_nodes[:10]:
                lines.append(f"- {title}")
            if len(invalid_nodes) > 10:
                lines.append(f"- ... and {len(invalid_nodes) - 10} more")
        else:
            lines.append("- None")

        lines.extend(
            [
                "",
                "Prompt Injection (applies to every LLM prompt)",
                f"- Enabled templates: {len(options.enabled_template_ids)}",
                f"- One-off placement: {one_off_placement}",
                "",
                f"Prepend blocks: {len(prepend_template_contents)}",
            ]
        )
        if prepend_template_contents:
            for idx, section in enumerate(prepend_template_contents, start=1):
                lines.append(f"[prepend #{idx}]")
                lines.append(section)
                lines.append("")
        else:
            lines.append("(none)")
            lines.append("")

        lines.append(f"Append blocks: {len(append_template_contents)}")
        if append_template_contents:
            for idx, section in enumerate(append_template_contents, start=1):
                lines.append(f"[append #{idx}]")
                lines.append(section)
                lines.append("")
        else:
            lines.append("(none)")
            lines.append("")

        lines.append("One-off block:")
        lines.append(one_off_text.strip() if one_off_text.strip() else "(none)")
        self._panel.set_overview_text("\n".join(lines))

    def _save(self):
        self._panel.commit_pending_edits()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Workflow",
            "",
            "JSON Files (*.json)",
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
            self,
            "Load Workflow",
            self.canvas._working_directory or os.getcwd(),
            "JSON Files (*.json)",
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
