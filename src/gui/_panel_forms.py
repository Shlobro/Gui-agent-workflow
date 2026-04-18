"""Form widgets used inside PropertiesPanel (one form class per node type)."""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .conditional_node import CONDITION_REGISTRY, condition_note, condition_requires_filename
from .checked_dropdown import CheckedDropdown
from .llm_widget import ModelSelector, populate_model_selector


class _LLMForm(QWidget):
    """Form widget for editing an LLMNode's properties."""

    _CALL_HEADER_RE = re.compile(r"^=== Call (\d+) ===$")
    _CALL_OUTPUT_FONT_BUMP = 1

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("LLM CALL")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        model_label = QLabel("Model")
        layout.addWidget(model_label)
        self.model_selector = ModelSelector(popup_parent=self)
        populate_model_selector(self.model_selector)
        layout.addWidget(self.model_selector)

        layout.addSpacing(4)

        self._resume_session_widget = QWidget()
        resume_session_layout = QVBoxLayout(self._resume_session_widget)
        resume_session_layout.setContentsMargins(0, 0, 0, 0)
        resume_session_layout.setSpacing(4)

        self.resume_session_checkbox = QCheckBox("Resume previous session")
        self.resume_session_checkbox.setToolTip(
            "Resume this node's previous Claude/Codex session on the next call."
        )
        resume_session_layout.addWidget(self.resume_session_checkbox)

        self.resume_session_note = QLabel("")
        self.resume_session_note.setWordWrap(True)
        self.resume_session_note.setVisible(False)
        resume_session_layout.addWidget(self.resume_session_note)

        layout.addWidget(self._resume_session_widget)
        layout.addSpacing(4)

        self.named_session_controls = QWidget()
        named_layout = QVBoxLayout(self.named_session_controls)
        named_layout.setContentsMargins(0, 0, 0, 0)
        named_layout.setSpacing(6)

        self.save_session_checkbox = QCheckBox("Save session ID")
        self.save_session_checkbox.setToolTip(
            "Store this node's captured Claude/Codex session under a workflow-level name."
        )
        named_layout.addWidget(self.save_session_checkbox)

        self.save_session_name_edit = QLineEdit()
        self.save_session_name_edit.setPlaceholderText("Saved session name...")
        named_layout.addWidget(self.save_session_name_edit)

        resume_named_label = QLabel("Resume session ID")
        named_layout.addWidget(resume_named_label)

        self.resume_named_session_combo = QComboBox()
        self.resume_named_session_combo.setPlaceholderText("")
        named_layout.addWidget(self.resume_named_session_combo)

        self.named_session_note = QLabel("")
        self.named_session_note.setWordWrap(True)
        self.named_session_note.setVisible(False)
        named_layout.addWidget(self.named_session_note)

        layout.addWidget(self.named_session_controls)

        layout.addSpacing(4)

        prepend_label = QLabel("Prepend")
        layout.addWidget(prepend_label)
        self.prepend_template_dropdown = CheckedDropdown(popup_parent=self)
        self.prepend_template_dropdown.set_placeholder_text("")
        layout.addWidget(self.prepend_template_dropdown)

        append_label = QLabel("Append")
        layout.addWidget(append_label)
        self.append_template_dropdown = CheckedDropdown(popup_parent=self)
        self.append_template_dropdown.set_placeholder_text("")
        layout.addWidget(self.append_template_dropdown)

        layout.addSpacing(4)

        self.prompt_warning_label = QLabel("")
        self.prompt_warning_label.setObjectName("warning_label")
        self.prompt_warning_label.setWordWrap(True)
        self.prompt_warning_label.setVisible(False)
        layout.addWidget(self.prompt_warning_label)

        layout.addSpacing(2)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)
        layout.addWidget(self._tabs, stretch=1)

        self._prompt_tab = QWidget()
        prompt_tab_layout = QVBoxLayout(self._prompt_tab)
        prompt_tab_layout.setContentsMargins(0, 0, 0, 0)
        prompt_tab_layout.setSpacing(0)

        self._prompt_frame = QFrame()
        prompt_container_layout = QVBoxLayout(self._prompt_frame)
        prompt_container_layout.setContentsMargins(0, 0, 0, 0)
        prompt_container_layout.setSpacing(4)

        self._prompt_splitter = QSplitter(Qt.Orientation.Vertical)
        self._prompt_splitter.setChildrenCollapsible(False)

        prompt_editor_frame = QFrame()
        prompt_layout = QVBoxLayout(prompt_editor_frame)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(4)
        prompt_label = QLabel("Prompt")
        prompt_layout.addWidget(prompt_label)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Enter your prompt here...")
        self.prompt_edit.setMinimumHeight(100)
        self.prompt_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        prompt_layout.addWidget(self.prompt_edit)
        self._prompt_splitter.addWidget(prompt_editor_frame)

        preview_frame = QFrame()
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)
        preview_label = QLabel("Prompt Preview")
        preview_layout.addWidget(preview_label)
        self.prompt_preview_edit = QPlainTextEdit()
        self.prompt_preview_edit.setReadOnly(True)
        self.prompt_preview_edit.setPlaceholderText(
            "Composed prompt preview will appear here."
        )
        self.prompt_preview_edit.setMinimumHeight(100)
        preview_layout.addWidget(self.prompt_preview_edit)
        self._prompt_splitter.addWidget(preview_frame)
        self._prompt_splitter.setSizes([4, 1])

        prompt_container_layout.addWidget(self._prompt_splitter)
        prompt_tab_layout.addWidget(self._prompt_frame)
        self._tabs.addTab(self._prompt_tab, "Prompt")

        self._output_tab = QWidget()
        output_tab_layout = QVBoxLayout(self._output_tab)
        output_tab_layout.setContentsMargins(0, 0, 0, 0)
        output_tab_layout.setSpacing(4)

        self._output_frame = QFrame()
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Output")
        out_layout.addWidget(self.output_label)
        self.output_tabs = QTabWidget()
        self.output_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.output_tabs.setDocumentMode(True)
        self.output_tabs.setVisible(False)
        out_layout.addWidget(self.output_tabs, stretch=1)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(80)
        self.output_edit.setPlaceholderText("No output yet.")
        out_layout.addWidget(self.output_edit)
        output_tab_layout.addWidget(self._output_frame, stretch=1)
        self._tabs.addTab(self._output_tab, "Output")

        self._call_editors: list[QPlainTextEdit] = []

    def set_resume_session_state(self, checked: bool, enabled: bool, note: str = "") -> None:
        self._resume_session_widget.setVisible(bool(enabled))
        self.resume_session_checkbox.blockSignals(True)
        self.resume_session_checkbox.setChecked(bool(checked))
        self.resume_session_checkbox.blockSignals(False)
        normalized_note = note.strip()
        self.resume_session_note.setText(normalized_note)
        self.resume_session_note.setVisible(bool(normalized_note))

    def set_named_session_controls_visible(self, visible: bool) -> None:
        self.named_session_controls.setVisible(bool(visible))

    def set_named_session_state(
        self,
        *,
        save_enabled: bool,
        save_name: str,
        resume_name: str,
        options: list[tuple[str, str]],
        note: str = "",
    ) -> None:
        self.save_session_checkbox.blockSignals(True)
        self.save_session_name_edit.blockSignals(True)
        self.resume_named_session_combo.blockSignals(True)

        self.save_session_checkbox.setChecked(bool(save_enabled))
        self.save_session_name_edit.setText(save_name)

        self.resume_named_session_combo.clear()
        for value, label in options:
            self.resume_named_session_combo.addItem(label, userData=value)

        target_index = -1
        for index in range(self.resume_named_session_combo.count()):
            if self.resume_named_session_combo.itemData(index) == resume_name:
                target_index = index
                break
        self.resume_named_session_combo.setCurrentIndex(target_index)

        self.save_session_checkbox.blockSignals(False)
        self.save_session_name_edit.blockSignals(False)
        self.resume_named_session_combo.blockSignals(False)

        save_blocked = bool(resume_name)
        self.save_session_checkbox.setEnabled(not save_blocked)
        self.save_session_name_edit.setEnabled(bool(save_enabled) and not save_blocked)

        normalized_note = note.strip()
        self.named_session_note.setText(normalized_note)
        self.named_session_note.setVisible(bool(normalized_note))

    def set_prompt_template_options(
        self,
        options: list[tuple[str, str]],
        *,
        checked_prepend_ids: list[str],
        checked_append_ids: list[str],
    ) -> None:
        self.prepend_template_dropdown.set_items(options)
        self.append_template_dropdown.set_items(options)
        self.prepend_template_dropdown.set_checked_ids(checked_prepend_ids)
        self.append_template_dropdown.set_checked_ids(checked_append_ids)

    def show_output(self, visible: bool):
        _ = visible
        self._tabs.setTabEnabled(1, True)

    def clear_output(self) -> None:
        self.output_edit.clear()
        self.output_edit.setVisible(True)
        while self.output_tabs.count():
            self.output_tabs.removeTab(0)
        self._call_editors.clear()
        self.output_tabs.setVisible(False)

    def set_output_text(self, text: str) -> None:
        self.clear_output()
        call_blocks = self._parse_call_blocks(text.splitlines())
        if not call_blocks:
            self.output_edit.setPlainText(text)
            return

        self.output_edit.setVisible(False)
        self.output_tabs.setVisible(True)
        for call_number, call_lines in call_blocks:
            editor = self._create_call_editor()
            editor.setPlainText("\n".join(call_lines).rstrip("\n"))
            self.output_tabs.addTab(editor, f"Call {call_number}")
            self._call_editors.append(editor)
        self.output_tabs.setCurrentIndex(self.output_tabs.count() - 1)

    def append_output_line(self, line: str) -> None:
        match = self._CALL_HEADER_RE.fullmatch(line.strip())
        if match:
            call_number = match.group(1)
            editor = self._create_call_editor()
            self.output_edit.setVisible(False)
            self.output_tabs.setVisible(True)
            self.output_tabs.addTab(editor, f"Call {call_number}")
            self._call_editors.append(editor)
            self.output_tabs.setCurrentIndex(self.output_tabs.count() - 1)
            return

        if self._call_editors:
            self._call_editors[-1].appendPlainText(line)
            return

        self.output_edit.appendPlainText(line)

    def _create_call_editor(self) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setMinimumHeight(80)
        editor.setPlaceholderText("No output yet.")
        editor.setObjectName("llm_call_output_edit")
        font = editor.font()
        base_size = max(font.pointSize(), self.output_edit.font().pointSize(), 8)
        font.setPointSize(base_size + self._CALL_OUTPUT_FONT_BUMP)
        editor.setFont(font)
        return editor

    @classmethod
    def _parse_call_blocks(cls, lines: list[str]) -> list[tuple[int, list[str]]]:
        blocks: list[tuple[int, list[str]]] = []
        current_call_number: int | None = None
        current_lines: list[str] = []
        saw_call_header = False

        for line in lines:
            match = cls._CALL_HEADER_RE.fullmatch(line.strip())
            if match:
                saw_call_header = True
                if current_call_number is not None:
                    blocks.append((current_call_number, current_lines))
                current_call_number = int(match.group(1))
                current_lines = []
                continue
            if current_call_number is not None:
                current_lines.append(line)

        if current_call_number is not None:
            blocks.append((current_call_number, current_lines))

        if not saw_call_header:
            return []
        return blocks


_OP_TYPE_OPTIONS = [
    ("create_file", "Create File"),
    ("truncate_file", "Truncate File"),
    ("delete_file", "Delete File"),
]


class _FileOpForm(QWidget):
    """Form widget for editing a FileOpNode's properties."""

    op_type_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("FILE OP")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        op_label = QLabel("Operation")
        layout.addWidget(op_label)
        self.op_type_combo = QComboBox()
        for key, display in _OP_TYPE_OPTIONS:
            self.op_type_combo.addItem(display, userData=key)
        layout.addWidget(self.op_type_combo)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        fn_label = QLabel("Filename")
        layout.addWidget(fn_label)
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("e.g. output.txt")
        layout.addWidget(self.filename_edit)

        layout.addSpacing(4)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Result")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(60)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        layout.addStretch(1)

        self._current_op_type: str = "create_file"
        self.op_type_combo.currentIndexChanged.connect(self._on_op_type_index_changed)

    def _on_op_type_index_changed(self, index: int):
        new_type = self.op_type_combo.itemData(index)
        if new_type and new_type != self._current_op_type:
            old = self._current_op_type
            self._current_op_type = new_type
            self.op_type_changed.emit(old, new_type)

    def set_op_type(self, node_type: str):
        self.op_type_combo.blockSignals(True)
        for index in range(self.op_type_combo.count()):
            if self.op_type_combo.itemData(index) == node_type:
                self.op_type_combo.setCurrentIndex(index)
                break
        self._current_op_type = node_type
        self.op_type_combo.blockSignals(False)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


class _ConditionalForm(QWidget):
    """Form widget for editing a ConditionalNode's properties."""

    condition_type_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("CONDITION")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        cond_label = QLabel("Condition")
        layout.addWidget(cond_label)
        self.condition_combo = QComboBox()
        for cond_id, meta in CONDITION_REGISTRY.items():
            self.condition_combo.addItem(meta["display_name"], userData=cond_id)
        layout.addWidget(self.condition_combo)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        self.filename_label = QLabel("File to check")
        layout.addWidget(self.filename_label)
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("e.g. output.txt")
        layout.addWidget(self.filename_edit)

        self.scope_note = QLabel("")
        self.scope_note.setWordWrap(True)
        self.scope_note.setVisible(False)
        layout.addWidget(self.scope_note)

        layout.addSpacing(4)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Result")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(60)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        layout.addStretch(1)

        self._current_condition_type: str = "file_empty"
        self.condition_combo.currentIndexChanged.connect(self._on_condition_index_changed)
        self._refresh_condition_inputs()

    def _on_condition_index_changed(self, index: int):
        new_type = self.condition_combo.itemData(index)
        if new_type and new_type != self._current_condition_type:
            old = self._current_condition_type
            self._current_condition_type = new_type
            self.condition_type_changed.emit(old, new_type)
        self._refresh_condition_inputs()

    def set_condition_type(self, condition_type: str):
        self.condition_combo.blockSignals(True)
        for index in range(self.condition_combo.count()):
            if self.condition_combo.itemData(index) == condition_type:
                self.condition_combo.setCurrentIndex(index)
                break
        self._current_condition_type = condition_type
        self.condition_combo.blockSignals(False)
        self._refresh_condition_inputs()

    def _refresh_condition_inputs(self):
        needs_filename = condition_requires_filename(self._current_condition_type)
        self.filename_label.setVisible(needs_filename)
        self.filename_edit.setVisible(needs_filename)
        note = condition_note(self._current_condition_type)
        self.scope_note.setText(note)
        self.scope_note.setVisible(bool(note) and not needs_filename)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


class _LoopForm(QWidget):
    """Form widget for editing a LoopNode's properties."""

    loop_count_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("LOOP")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        count_label = QLabel("Iterations (N)")
        layout.addWidget(count_label)
        self.count_spin = QSpinBox()
        self.count_spin.setMinimum(1)
        self.count_spin.setMaximum(9999)
        self.count_spin.setValue(3)
        layout.addWidget(self.count_spin)

        layout.addSpacing(4)

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

        layout.addStretch(1)

        self._current_count: int = 3
        self.count_spin.valueChanged.connect(self._on_count_changed)

    def _on_count_changed(self, value: int):
        if value != self._current_count:
            old = self._current_count
            self._current_count = value
            self.loop_count_changed.emit(old, value)

    def set_loop_count(self, count: int):
        self.count_spin.blockSignals(True)
        self.count_spin.setValue(count)
        self._current_count = self.count_spin.value()
        self.count_spin.blockSignals(False)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


class _JoinForm(QWidget):
    """Form widget for editing a JoinNode's properties."""

    wait_for_count_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("JOIN")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        wait_label = QLabel("Wait For Arrivals")
        layout.addWidget(wait_label)
        self.count_spin = QSpinBox()
        self.count_spin.setMinimum(1)
        self.count_spin.setMaximum(9999)
        self.count_spin.setValue(2)
        layout.addWidget(self.count_spin)

        layout.addSpacing(4)

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

        layout.addStretch(1)

        self._current_count: int = 2
        self.count_spin.valueChanged.connect(self._on_count_changed)

    def _on_count_changed(self, value: int):
        if value != self._current_count:
            old = self._current_count
            self._current_count = value
            self.wait_for_count_changed.emit(old, value)

    def set_wait_for_count(self, count: int):
        self.count_spin.blockSignals(True)
        self.count_spin.setValue(count)
        self._current_count = self.count_spin.value()
        self.count_spin.blockSignals(False)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


_GIT_ACTION_OPTIONS = [
    ("git_add", "Git Add"),
    ("git_commit", "Git Commit"),
    ("git_push", "Git Push"),
]

_MSG_SOURCE_OPTIONS = [
    ("static", "Static text"),
    ("from_file", "From file"),
]


class _GitActionForm(QWidget):
    """Form widget for editing a GitActionNode's properties."""

    git_action_changed = Signal(str, str)
    msg_source_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("GIT ACTION")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        action_label = QLabel("Action")
        layout.addWidget(action_label)
        self.action_combo = QComboBox()
        for key, display in _GIT_ACTION_OPTIONS:
            self.action_combo.addItem(display, userData=key)
        layout.addWidget(self.action_combo)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        self._commit_frame = QFrame()
        commit_layout = QVBoxLayout(self._commit_frame)
        commit_layout.setContentsMargins(0, 0, 0, 0)
        commit_layout.setSpacing(6)

        src_label = QLabel("Message source")
        commit_layout.addWidget(src_label)
        self.msg_source_combo = QComboBox()
        for key, display in _MSG_SOURCE_OPTIONS:
            self.msg_source_combo.addItem(display, userData=key)
        commit_layout.addWidget(self.msg_source_combo)

        commit_layout.addSpacing(2)

        self.commit_msg_edit = QLineEdit()
        self.commit_msg_edit.setPlaceholderText("Commit message...")
        commit_layout.addWidget(self.commit_msg_edit)

        self.commit_msg_file_edit = QLineEdit()
        self.commit_msg_file_edit.setPlaceholderText("e.g. commit_msg.txt")
        commit_layout.addWidget(self.commit_msg_file_edit)

        layout.addWidget(self._commit_frame)

        layout.addSpacing(4)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Result")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(60)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        layout.addStretch(1)

        self._current_action: str = "git_add"
        self._current_msg_source: str = "static"
        self.action_combo.currentIndexChanged.connect(self._on_action_index_changed)
        self.msg_source_combo.currentIndexChanged.connect(self._on_msg_source_changed)

        self._refresh_commit_frame_visibility()
        self._refresh_msg_source_visibility()

    def _on_action_index_changed(self, index: int):
        new_action = self.action_combo.itemData(index)
        if new_action and new_action != self._current_action:
            old = self._current_action
            self._current_action = new_action
            self.git_action_changed.emit(old, new_action)
        self._refresh_commit_frame_visibility()

    def _on_msg_source_changed(self, _index: int):
        new_source = self.msg_source_combo.currentData()
        if new_source and new_source != self._current_msg_source:
            old = self._current_msg_source
            self._current_msg_source = new_source
            self.msg_source_changed.emit(old, new_source)
        self._refresh_msg_source_visibility()

    def _refresh_commit_frame_visibility(self):
        self._commit_frame.setVisible(self._current_action == "git_commit")

    def _refresh_msg_source_visibility(self):
        source = self.msg_source_combo.currentData()
        self.commit_msg_edit.setVisible(source != "from_file")
        self.commit_msg_file_edit.setVisible(source == "from_file")

    def set_git_action(self, action: str):
        self.action_combo.blockSignals(True)
        for index in range(self.action_combo.count()):
            if self.action_combo.itemData(index) == action:
                self.action_combo.setCurrentIndex(index)
                break
        self._current_action = action
        self.action_combo.blockSignals(False)
        self._refresh_commit_frame_visibility()

    def set_msg_source(self, source: str):
        self.msg_source_combo.blockSignals(True)
        matched = False
        for index in range(self.msg_source_combo.count()):
            if self.msg_source_combo.itemData(index) == source:
                self.msg_source_combo.setCurrentIndex(index)
                matched = True
                break
        if matched:
            self._current_msg_source = source
        else:
            self._current_msg_source = self.msg_source_combo.currentData() or "static"
        self.msg_source_combo.blockSignals(False)
        self._refresh_msg_source_visibility()

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


class _AttentionForm(QWidget):
    """Form widget for editing an AttentionNode's properties."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("ATTENTION")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        message_label = QLabel("Message")
        layout.addWidget(message_label)
        self.message_edit = QPlainTextEdit()
        self.message_edit.setPlaceholderText("What should the user be told when this node runs?")
        self.message_edit.setMinimumHeight(100)
        self.message_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.message_edit, stretch=1)

        layout.addSpacing(4)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Result")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(60)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


class _ScriptForm(QWidget):
    """Form widget for editing a ScriptNode's properties."""

    browse_requested = Signal()
    auto_send_enter_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("SCRIPT")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name...")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        path_label = QLabel("Script Path")
        layout.addWidget(path_label)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(6)
        self.script_path_edit = QLineEdit()
        self.script_path_edit.setPlaceholderText(r"e.g. scripts\build.ps1")
        path_row.addWidget(self.script_path_edit, stretch=1)
        self.browse_button = QPushButton("Browse...")
        path_row.addWidget(self.browse_button)
        layout.addLayout(path_row)

        note = QLabel("Supported: .bat, .cmd, .ps1 inside the selected project folder.")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addSpacing(4)

        self.auto_send_enter_checkbox = QCheckBox("Send Enter automatically to stdin")
        layout.addWidget(self.auto_send_enter_checkbox)

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

        layout.addStretch(1)
        self.browse_button.clicked.connect(self.browse_requested.emit)
        self.auto_send_enter_checkbox.toggled.connect(self.auto_send_enter_changed)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)
