"""Helpers for loading and refreshing the LLM properties form."""

from __future__ import annotations

from src.llm.prompt_injection import (
    compose_prompt,
    effective_node_template_ids,
    resolve_template_contents_for_ids,
)
from src.gui.workflow_io import get_provider_for_model


def load_llm_form(panel, node) -> None:
    form = panel._llm_form
    form.title_edit.blockSignals(True)
    form.model_selector.blockSignals(True)
    form.prompt_edit.blockSignals(True)

    form.title_edit.setText(node.title)
    form.model_selector.set_model_id(node.model_id)
    refresh_llm_session_state(panel, node)
    form.prompt_edit.setPlainText(node.prompt_text)
    refresh_llm_template_controls(panel, node)

    if node.output_text:
        form.set_output_text(node.output_text.rstrip("\n"))
        form.show_output(True)
    else:
        form.clear_output()
        form.show_output(False)

    form.title_edit.blockSignals(False)
    form.model_selector.blockSignals(False)
    form.prompt_edit.blockSignals(False)

    panel._old_title = node.title
    panel._prompt_dirty = False
    panel._save_session_name_dirty = False
    refresh_llm_prompt_preview(panel)


def refresh_llm_template_controls(panel, node) -> None:
    panel._llm_form.set_prompt_template_options(
        [
            (template.template_id, template.name)
            for template in panel._prompt_injection_config.templates
        ],
        checked_prepend_ids=list(
            effective_node_template_ids(
                panel._prompt_injection_config,
                panel._persistent_global_template_ids,
                node.prepend_template_ids,
                node.prepend_disabled_global_template_ids,
            )
        ),
        checked_append_ids=list(
            effective_node_template_ids(
                panel._prompt_injection_config,
                panel._persistent_global_template_ids,
                node.append_template_ids,
                node.append_disabled_global_template_ids,
            )
        ),
    )


def refresh_llm_prompt_preview(panel) -> None:
    node = panel._current_node
    if node is None:
        return
    prompt_text = panel._llm_form.prompt_edit.toPlainText()
    warning_note = ""
    if panel._llm_prompt_preview_provider is not None:
        prompt_text, warnings = panel._llm_prompt_preview_provider(node, prompt_text)
        warning_note = "\n".join(warnings)
    panel._llm_form.prompt_warning_label.setText(warning_note)
    panel._llm_form.prompt_warning_label.setVisible(bool(warning_note))
    prepend_template_contents = resolve_template_contents_for_ids(
        panel._prompt_injection_config,
        effective_node_template_ids(
            panel._prompt_injection_config,
            panel._preview_global_template_ids,
            node.prepend_template_ids,
            node.prepend_disabled_global_template_ids,
        ),
    )
    append_template_contents = resolve_template_contents_for_ids(
        panel._prompt_injection_config,
        effective_node_template_ids(
            panel._prompt_injection_config,
            panel._preview_global_template_ids,
            node.append_template_ids,
            node.append_disabled_global_template_ids,
        ),
    )
    preview_text = compose_prompt(
        prompt_text,
        prepend_template_contents,
        append_template_contents,
        panel._preview_one_off_text,
        panel._preview_one_off_placement,
    )
    panel._llm_form.prompt_preview_edit.setPlainText(preview_text)


def refresh_llm_session_state(panel, node) -> None:
    provider = get_provider_for_model(node.model_id or "")
    supports_resume = bool(provider and provider.supports_session_resume(node.model_id))
    note = ""
    if node.resume_named_session_name:
        note = "Named session resume uses the saved workflow session and disables saving a new name here."
    panel._llm_form.set_resume_session_state(
        bool(node.resume_session_enabled) if supports_resume else False,
        supports_resume,
    )
    panel._llm_form.set_named_session_controls_visible(supports_resume)
    panel._llm_form.set_named_session_state(
        save_enabled=bool(node.save_session_enabled),
        save_name=node.save_session_name,
        resume_name=node.resume_named_session_name,
        options=list(panel._llm_named_session_options),
        note=note,
    )
