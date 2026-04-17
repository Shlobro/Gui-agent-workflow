"""Named-session handlers extracted from MainWindow."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from src.gui.llm_node import LLMNode
from src.gui.workflow_io import get_provider_for_model


def refresh_llm_panel_for_node(main_window, node) -> None:
    if not isinstance(node, LLMNode):
        return
    provider = get_provider_for_model(node.model_id or "")
    provider_name = (
        provider.name if provider and provider.supports_session_resume(node.model_id) else ""
    )
    options = main_window.canvas.available_named_session_options_for_node(
        node.node_id, provider_name
    )
    main_window._panel.set_llm_named_session_options(options)


def handle_panel_model_changed(main_window, node_id: str, old_model_id: str, new_model_id: str) -> None:
    node = main_window.canvas._nodes.get(node_id)
    if node is None or not isinstance(node, LLMNode):
        return
    old_provider = get_provider_for_model(old_model_id)
    new_provider = get_provider_for_model(new_model_id)
    old_state = main_window.canvas.llm_node_state(node_id)
    if old_state is None:
        return
    old_named_sessions = main_window.canvas.named_sessions_snapshot()
    new_resume_enabled = bool(old_state["resume_session_enabled"])
    new_saved_session_id = str(old_state["saved_session_id"])
    new_saved_session_provider = str(old_state["saved_session_provider"])
    clear_captured_session_data = False
    owned_named_record = main_window.canvas.named_session_record(node.save_session_name)
    owns_saved_named_session = bool(
        owned_named_record is not None
        and owned_named_record.get("owner_node_id") == node_id
        and owned_named_record.get("session_id", "").strip()
    )
    if (str(old_state["saved_session_id"]).strip() or owns_saved_named_session) and old_model_id != new_model_id:
        reply = QMessageBox.question(
            main_window,
            "Delete Saved Session?",
            "Changing the model will delete this node's saved LLM session data.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            main_window._panel.refresh_if_current(node)
            return
        new_saved_session_id = ""
        new_saved_session_provider = ""
        clear_captured_session_data = True
    if new_provider is None or not new_provider.supports_session_resume(new_model_id):
        new_resume_enabled = False
    old_provider_name = old_provider.name if old_provider is not None else ""
    new_provider_name = new_provider.name if new_provider is not None else ""
    if new_provider is None or not new_provider.supports_session_resume(new_model_id):
        named_state, new_named_sessions = main_window.canvas.build_named_session_update(
            node_id,
            save_enabled=False,
            save_name="",
            resume_name="",
            model_id=new_model_id,
        )
    elif old_provider_name != new_provider_name:
        named_state, new_named_sessions = main_window.canvas.build_named_session_update(
            node_id,
            save_enabled=bool(old_state["save_session_enabled"]),
            save_name=str(old_state["save_session_name"]),
            resume_name="",
            model_id=new_model_id,
        )
    else:
        named_state, new_named_sessions = main_window.canvas.build_named_session_update(
            node_id,
            save_enabled=bool(old_state["save_session_enabled"]),
            save_name=str(old_state["save_session_name"]),
            resume_name=str(old_state["resume_named_session_name"]),
            model_id=new_model_id,
        )
    new_state = dict(old_state)
    new_state.update(
        {
            "model_id": new_model_id,
            "resume_session_enabled": new_resume_enabled,
            "save_session_enabled": bool(named_state["save_session_enabled"]),
            "save_session_name": str(named_state["save_session_name"]),
            "resume_named_session_name": str(named_state["resume_named_session_name"]),
            "saved_session_id": new_saved_session_id,
            "saved_session_provider": new_saved_session_provider,
        }
    )
    if clear_captured_session_data:
        owned_name = str(new_state["save_session_name"]).strip()
        if owned_name:
            owned_record = new_named_sessions.get(owned_name)
            if owned_record is not None and owned_record.get("owner_node_id") == node_id:
                owned_record["session_id"] = ""
    main_window.canvas._on_model_changed(
        node_id,
        old_state,
        new_state,
        old_named_sessions,
        new_named_sessions,
    )
    refresh_llm_panel_for_node(main_window, node)
    main_window._panel.refresh_if_current(node)
    main_window._refresh_panel_overview()


def handle_panel_save_session_changed(main_window, node_id: str, checked: bool) -> None:
    node = main_window.canvas._nodes.get(node_id)
    if node is None or not isinstance(node, LLMNode):
        return
    old_state = main_window.canvas.llm_node_state(node_id)
    if old_state is None:
        return
    old_named_sessions = main_window.canvas.named_sessions_snapshot()
    try:
        new_state, new_named_sessions = main_window.canvas.build_named_session_update(
            node_id,
            save_enabled=checked,
        )
    except ValueError as exc:
        QMessageBox.warning(main_window, "Session Name In Use", str(exc))
        refresh_llm_panel_for_node(main_window, node)
        main_window._panel.refresh_if_current(node)
        return
    main_window.canvas._on_named_session_config_changed(
        node_id,
        old_state=old_state,
        new_state=new_state,
        old_named_sessions=old_named_sessions,
        new_named_sessions=new_named_sessions,
        command_text="Toggle Save Session ID",
    )
    refresh_llm_panel_for_node(main_window, node)
    main_window._panel.refresh_if_current(node)
    main_window._refresh_panel_overview()


def handle_panel_save_session_name_committed(main_window, node_id: str, text: str) -> None:
    node = main_window.canvas._nodes.get(node_id)
    if node is None or not isinstance(node, LLMNode):
        return
    old_state = main_window.canvas.llm_node_state(node_id)
    if old_state is None:
        return
    old_named_sessions = main_window.canvas.named_sessions_snapshot()
    try:
        new_state, new_named_sessions = main_window.canvas.build_named_session_update(
            node_id,
            save_name=text.strip(),
        )
    except ValueError as exc:
        QMessageBox.warning(main_window, "Session Name In Use", str(exc))
        refresh_llm_panel_for_node(main_window, node)
        main_window._panel.refresh_if_current(node)
        return
    main_window.canvas._on_named_session_config_changed(
        node_id,
        old_state=old_state,
        new_state=new_state,
        old_named_sessions=old_named_sessions,
        new_named_sessions=new_named_sessions,
        command_text="Rename Saved Session ID",
    )
    refresh_llm_panel_for_node(main_window, node)
    main_window._panel.refresh_if_current(node)
    main_window._refresh_panel_overview()


def handle_panel_resume_named_session_changed(main_window, node_id: str, session_name: str) -> None:
    node = main_window.canvas._nodes.get(node_id)
    if node is None or not isinstance(node, LLMNode):
        return
    old_state = main_window.canvas.llm_node_state(node_id)
    if old_state is None:
        return
    old_named_sessions = main_window.canvas.named_sessions_snapshot()
    new_state, new_named_sessions = main_window.canvas.build_named_session_update(
        node_id,
        resume_name=session_name,
    )
    main_window.canvas._on_named_session_config_changed(
        node_id,
        old_state=old_state,
        new_state=new_state,
        old_named_sessions=old_named_sessions,
        new_named_sessions=new_named_sessions,
        command_text="Change Resume Session ID",
    )
    refresh_llm_panel_for_node(main_window, node)
    main_window._panel.refresh_if_current(node)
    main_window._refresh_panel_overview()
