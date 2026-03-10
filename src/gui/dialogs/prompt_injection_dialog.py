"""Dialogs for prompt injection templates and per-run injection overrides."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from src.llm.prompt_injection import (
    MAX_ONE_OFF_INJECTION_CHARS,
    PromptInjectionConfig,
    PromptInjectionRunOptions,
    PromptTemplate,
    create_user_template,
    normalize_one_off_text,
    normalize_run_options,
    unique_existing_template_ids,
)

_STYLE = """
QDialog {
    background: #1e1e1e;
    color: #e8e8e8;
}
QLabel {
    color: #e8e8e8;
}
QLineEdit, QPlainTextEdit, QListWidget {
    background: #151515;
    color: #e8e8e8;
    border: 1px solid #444;
    border-radius: 4px;
}
QLineEdit, QPlainTextEdit {
    padding: 6px;
}
QPushButton {
    background: #333;
    color: #e8e8e8;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:hover { background: #444; }
QPushButton:disabled { color: #777; border-color: #3d3d3d; }
"""


class _TemplateEditorDialog(QDialog):
    def __init__(self, title: str, name: str = "", content: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._name_edit = QLineEdit()
        self._name_edit.setText(name)
        self._content_edit = QPlainTextEdit()
        self._content_edit.setPlainText(content)
        self._content_edit.setMinimumHeight(220)
        form.addRow("Template name", self._name_edit)
        form.addRow("Template content", self._content_edit)
        layout.addLayout(form)

        note = QLabel(
            "Templates are injected into every LLM prompt when enabled."
        )
        note.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def template_name(self) -> str:
        return self._name_edit.text()

    def template_content(self) -> str:
        return self._content_edit.toPlainText()


class PromptTemplateManagerDialog(QDialog):
    """Manage saved prompt templates and default enabled templates."""

    def __init__(self, config: PromptInjectionConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt Templates")
        self.setModal(True)
        self.setMinimumSize(760, 460)
        self.setStyleSheet(_STYLE)
        self._templates = list(config.templates)
        self._default_enabled_ids = set(config.default_enabled_template_ids)
        self._result_config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        info = QLabel(
            "Checked templates are enabled by default for each run. "
            "Built-in templates cannot be edited or deleted."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaaaaa;")
        root.addWidget(info)

        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, stretch=1)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        body.addWidget(self._list, stretch=1)

        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        body.addWidget(self._preview, stretch=2)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self._add_btn = QPushButton("Add")
        self._edit_btn = QPushButton("Edit")
        self._delete_btn = QPushButton("Delete")
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add)
        self._edit_btn.clicked.connect(self._on_edit)
        self._delete_btn.clicked.connect(self._on_delete)
        button_row.addWidget(self._add_btn)
        button_row.addWidget(self._edit_btn)
        button_row.addWidget(self._delete_btn)
        button_row.addStretch(1)
        root.addLayout(button_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._rebuild_list()

    def result_config(self) -> PromptInjectionConfig:
        return self._result_config

    def _on_selection_changed(self) -> None:
        current = self._current_template()
        can_edit = current is not None and not current.built_in
        self._edit_btn.setEnabled(can_edit)
        self._delete_btn.setEnabled(can_edit)
        if current is None:
            self._preview.setPlainText("")
            return
        self._preview.setPlainText(current.content)

    def _rebuild_list(self) -> None:
        if self._list.count() > 0:
            self._default_enabled_ids = set(self._checked_template_ids())
        self._list.blockSignals(True)
        self._list.clear()
        for template in self._templates:
            label = template.name
            if template.built_in:
                label = f"{label} (built-in)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, template.template_id)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if template.template_id in self._default_enabled_ids
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        self._list.blockSignals(False)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._preview.setPlainText("")
            self._edit_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)

    def _current_template(self) -> PromptTemplate | None:
        item = self._list.currentItem()
        if item is None:
            return None
        template_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        for template in self._templates:
            if template.template_id == template_id:
                return template
        return None

    def _name_conflict(self, name: str, ignore_id: str | None = None) -> bool:
        target = name.casefold()
        for template in self._templates:
            if ignore_id and template.template_id == ignore_id:
                continue
            if template.name.casefold() == target:
                return True
        return False

    def _on_add(self) -> None:
        dialog = _TemplateEditorDialog("Add Template", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            template = create_user_template(
                name=dialog.template_name(),
                content=dialog.template_content(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Template", str(exc))
            return
        if self._name_conflict(template.name):
            QMessageBox.warning(self, "Duplicate Name", "Template name must be unique.")
            return
        self._templates.append(template)
        self._rebuild_list()
        self._select_template(template.template_id)

    def _on_edit(self) -> None:
        template = self._current_template()
        if template is None:
            return
        dialog = _TemplateEditorDialog(
            "Edit Template",
            name=template.name,
            content=template.content,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            updated = create_user_template(
                name=dialog.template_name(),
                content=dialog.template_content(),
                template_id=template.template_id,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Template", str(exc))
            return
        if self._name_conflict(updated.name, ignore_id=template.template_id):
            QMessageBox.warning(self, "Duplicate Name", "Template name must be unique.")
            return
        for idx, existing in enumerate(self._templates):
            if existing.template_id == template.template_id:
                self._templates[idx] = updated
                break
        self._rebuild_list()
        self._select_template(template.template_id)

    def _on_delete(self) -> None:
        template = self._current_template()
        if template is None:
            return
        if template.built_in:
            QMessageBox.information(
                self,
                "Built-In Template",
                "Built-in templates cannot be deleted.",
            )
            return
        reply = QMessageBox.question(
            self,
            "Delete Template",
            f'Delete template "{template.name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._templates = [
            existing
            for existing in self._templates
            if existing.template_id != template.template_id
        ]
        self._default_enabled_ids.discard(template.template_id)
        self._rebuild_list()

    def _select_template(self, template_id: str) -> None:
        for idx in range(self._list.count()):
            item = self._list.item(idx)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == template_id:
                self._list.setCurrentRow(idx)
                return

    def _checked_template_ids(self) -> tuple[str, ...]:
        checked_ids: list[str] = []
        for idx in range(self._list.count()):
            item = self._list.item(idx)
            if item.checkState() == Qt.CheckState.Checked:
                checked_ids.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        return unique_existing_template_ids(
            PromptInjectionConfig(tuple(self._templates), tuple()),
            checked_ids,
        )

    def _on_save(self) -> None:
        config = PromptInjectionConfig(
            templates=tuple(self._templates),
            default_enabled_template_ids=self._checked_template_ids(),
        )
        self._result_config = config
        self.accept()


class PromptInjectionRunDialog(QDialog):
    """Set prompt injection options for the next workflow run only."""

    def __init__(
        self,
        config: PromptInjectionConfig,
        current: PromptInjectionRunOptions | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Prompt Injection - Next Run")
        self.setModal(True)
        self.setMinimumSize(700, 420)
        self.setStyleSheet(_STYLE)
        self._config = config
        normalized = normalize_run_options(config, current)
        self._result_options = normalized

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        info = QLabel(
            "Choose templates to inject on the next run. "
            "You can also provide one one-off block that is not saved."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaaaaa;")
        root.addWidget(info)

        self._list = QListWidget()
        root.addWidget(self._list, stretch=1)

        one_off_label = QLabel("One-off injection (next run only)")
        root.addWidget(one_off_label)
        self._one_off_edit = QPlainTextEdit()
        self._one_off_edit.setMinimumHeight(130)
        self._one_off_edit.setPlainText(normalized.one_off_text)
        root.addWidget(self._one_off_edit)

        char_note = QLabel(
            f"One-off max length: {MAX_ONE_OFF_INJECTION_CHARS} characters."
        )
        char_note.setStyleSheet("color: #888888;")
        root.addWidget(char_note)

        button_row = QHBoxLayout()
        defaults_btn = QPushButton("Use Saved Defaults")
        defaults_btn.clicked.connect(self._restore_defaults)
        button_row.addWidget(defaults_btn)
        button_row.addStretch(1)
        root.addLayout(button_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._rebuild_list(normalized.enabled_template_ids)

    def result_options(self) -> PromptInjectionRunOptions:
        return self._result_options

    def _rebuild_list(self, enabled_ids: Iterable[str]) -> None:
        enabled_set = set(enabled_ids)
        self._list.clear()
        for template in self._config.templates:
            label = template.name
            if template.built_in:
                label = f"{label} (built-in)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, template.template_id)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if template.template_id in enabled_set
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)

    def _checked_template_ids(self) -> tuple[str, ...]:
        checked: list[str] = []
        for idx in range(self._list.count()):
            item = self._list.item(idx)
            if item.checkState() == Qt.CheckState.Checked:
                checked.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        return unique_existing_template_ids(self._config, checked)

    def _restore_defaults(self) -> None:
        self._rebuild_list(self._config.default_enabled_template_ids)
        self._one_off_edit.setPlainText("")

    def _on_accept(self) -> None:
        try:
            one_off = normalize_one_off_text(self._one_off_edit.toPlainText())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid One-Off Injection", str(exc))
            return
        self._result_options = PromptInjectionRunOptions(
            enabled_template_ids=self._checked_template_ids(),
            one_off_text=one_off,
        )
        self.accept()
