"""WorkflowCanvas mixin for LLM session and named-session state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from src.gui.connection_item import ConnectionItem
from src.gui.llm_node import LLMNode, StartNode, WorkflowNode
from src.gui.workflow_io import get_provider_for_model
from src.gui.llm_sessions.session_state import (
    available_named_session_options,
    clone_named_sessions,
    count_saved_named_sessions,
    named_session_is_available,
    normalize_session_name,
)

if TYPE_CHECKING:
    from src.gui.canvas import WorkflowCanvas


class _SessionStateMixin:
    def llm_nodes_with_saved_sessions(self: "WorkflowCanvas") -> List[LLMNode]:
        return [
            node
            for node in self._nodes.values()
            if isinstance(node, LLMNode) and bool(node.saved_session_id.strip())
        ]

    def has_saved_llm_sessions(self: "WorkflowCanvas") -> bool:
        return bool(self.llm_nodes_with_saved_sessions()) or bool(
            count_saved_named_sessions(self._named_sessions)
        )

    def clear_all_llm_sessions(self: "WorkflowCanvas") -> None:
        for node in self._nodes.values():
            if not isinstance(node, LLMNode):
                continue
            node.saved_session_id = ""
            node.saved_session_provider = ""
        for record in self._named_sessions.values():
            record["session_id"] = ""
        self.reconcile_named_sessions()

    def named_sessions_snapshot(self: "WorkflowCanvas") -> Dict[str, Dict[str, str]]:
        return clone_named_sessions(self._named_sessions)

    def workflow_nodes(self: "WorkflowCanvas") -> List[WorkflowNode]:
        return list(self._nodes.values())

    def selected_workflow_nodes(self: "WorkflowCanvas") -> List[WorkflowNode]:
        return [
            item
            for item in self._scene.selectedItems()
            if isinstance(item, WorkflowNode) and not isinstance(item, StartNode)
        ]

    def selected_connection_items(self: "WorkflowCanvas") -> List[ConnectionItem]:
        return [
            item
            for item in self._scene.selectedItems()
            if isinstance(item, ConnectionItem)
        ]

    def connection_items(self: "WorkflowCanvas") -> List[ConnectionItem]:
        return list(self._connections)

    def connection_count(self: "WorkflowCanvas") -> int:
        return len(self._connections)

    def named_session_count(self: "WorkflowCanvas", *, saved_only: bool = False) -> int:
        if not saved_only:
            return len(self._named_sessions)
        return count_saved_named_sessions(self._named_sessions)

    def total_saved_session_count(self: "WorkflowCanvas") -> int:
        return len(self.llm_nodes_with_saved_sessions()) + self.named_session_count(
            saved_only=True
        )

    @staticmethod
    def _capture_named_session_fields(node: LLMNode) -> Dict[str, object]:
        return {
            "save_session_enabled": bool(node.save_session_enabled),
            "save_session_name": str(node.save_session_name or ""),
            "resume_named_session_name": str(node.resume_named_session_name or ""),
        }

    @staticmethod
    def _capture_llm_node_state(node: LLMNode) -> Dict[str, object]:
        return {
            "model_id": str(node.model_id or ""),
            "resume_session_enabled": bool(node.resume_session_enabled),
            "save_session_enabled": bool(node.save_session_enabled),
            "save_session_name": str(node.save_session_name or ""),
            "resume_named_session_name": str(node.resume_named_session_name or ""),
            "saved_session_id": str(node.saved_session_id or ""),
            "saved_session_provider": str(node.saved_session_provider or ""),
        }

    def llm_node_state(self: "WorkflowCanvas", node_id: str) -> Dict[str, object] | None:
        node = self._nodes.get(node_id)
        if not isinstance(node, LLMNode):
            return None
        return self._capture_llm_node_state(node)

    def named_sessions_owned_by(
        self: "WorkflowCanvas", node_id: str
    ) -> Dict[str, Dict[str, str]]:
        owned: Dict[str, Dict[str, str]] = {}
        for session_name, record in self._named_sessions.items():
            if record.get("owner_node_id") == node_id:
                owned[session_name] = dict(record)
        return owned

    def restore_named_sessions(
        self: "WorkflowCanvas", named_sessions: Dict[str, Dict[str, str]]
    ) -> None:
        for session_name, record in named_sessions.items():
            self._named_sessions[session_name] = dict(record)

    def available_named_session_options_for_node(
        self: "WorkflowCanvas", node_id: str, provider_name: str
    ) -> List[tuple[str, str]]:
        return available_named_session_options(
            self._named_sessions,
            self._connections,
            provider_name=provider_name,
            target_node_id=node_id,
        )

    def named_session_record(
        self: "WorkflowCanvas", session_name: str
    ) -> Dict[str, str] | None:
        return self._named_sessions.get(normalize_session_name(session_name))

    def build_named_session_update(
        self: "WorkflowCanvas",
        node_id: str,
        *,
        save_enabled: bool | None = None,
        save_name: str | None = None,
        resume_name: str | None = None,
        model_id: str | None = None,
    ) -> tuple[Dict[str, object], Dict[str, Dict[str, str]]]:
        node = self._nodes.get(node_id)
        if not isinstance(node, LLMNode):
            raise ValueError("Named session updates only apply to LLM nodes.")

        effective_model_id = node.model_id if model_id is None else model_id
        provider = get_provider_for_model(effective_model_id or "")
        supports_resume = bool(
            provider is not None and provider.supports_session_resume(effective_model_id)
        )
        provider_name = provider.name if supports_resume else ""
        next_named_sessions = clone_named_sessions(self._named_sessions)

        old_save_name = normalize_session_name(node.save_session_name)
        new_save_enabled = (
            node.save_session_enabled if save_enabled is None else bool(save_enabled)
        )
        new_save_name = (
            old_save_name if save_name is None else normalize_session_name(save_name)
        )
        new_resume_name = (
            normalize_session_name(node.resume_named_session_name)
            if resume_name is None
            else normalize_session_name(resume_name)
        )

        if not supports_resume:
            new_save_enabled = False
            new_save_name = ""
            new_resume_name = ""

        if new_resume_name:
            new_save_enabled = False

        old_owned_record = None
        if old_save_name:
            candidate_record = next_named_sessions.get(old_save_name)
            if (
                candidate_record is not None
                and candidate_record.get("owner_node_id") == node.node_id
            ):
                old_owned_record = dict(candidate_record)

        if old_save_name and (
            not node.save_session_enabled
            or old_save_name != new_save_name
            or not new_save_enabled
        ):
            record = next_named_sessions.get(old_save_name)
            if record is not None and record.get("owner_node_id") == node.node_id:
                next_named_sessions.pop(old_save_name, None)

        if new_save_enabled and new_save_name:
            existing = next_named_sessions.get(new_save_name)
            if existing is not None and existing.get("owner_node_id") != node.node_id:
                raise ValueError(
                    f'Session name "{new_save_name}" is already used by another node.'
                )
            preserved_session_id = ""
            if (
                old_owned_record is not None
                and old_owned_record.get("provider", "") == provider_name
            ):
                preserved_session_id = old_owned_record.get("session_id", "").strip()
            elif (
                node.saved_session_id.strip()
                and node.saved_session_provider.strip() == provider_name
            ):
                preserved_session_id = node.saved_session_id.strip()
            elif existing is not None and existing.get("provider", "") == provider_name:
                preserved_session_id = existing.get("session_id", "").strip()
            next_named_sessions[new_save_name] = {
                "owner_node_id": node.node_id,
                "provider": provider_name,
                "session_id": preserved_session_id,
            }

        next_state = {
            "save_session_enabled": bool(new_save_enabled),
            "save_session_name": new_save_name,
            "resume_named_session_name": new_resume_name,
        }

        if not supports_resume:
            next_state["save_session_enabled"] = False
            next_state["save_session_name"] = ""
            next_state["resume_named_session_name"] = ""

        if next_state["save_session_enabled"] and next_state["save_session_name"]:
            record = next_named_sessions.get(str(next_state["save_session_name"]))
            if record is None or record.get("owner_node_id") != node.node_id:
                next_state["save_session_enabled"] = False
        if next_state["resume_named_session_name"] and not named_session_is_available(
            next_named_sessions,
            self._connections,
            session_name=str(next_state["resume_named_session_name"]),
            provider_name=provider_name,
            target_node_id=node.node_id,
        ):
            next_state["resume_named_session_name"] = ""
        return next_state, next_named_sessions

    def apply_named_session_update(
        self: "WorkflowCanvas",
        node_id: str,
        node_state: Dict[str, object],
        named_sessions: Dict[str, Dict[str, str]],
    ) -> None:
        node = self._nodes.get(node_id)
        if not isinstance(node, LLMNode):
            return
        node.save_session_enabled = bool(node_state.get("save_session_enabled", False))
        node.save_session_name = str(node_state.get("save_session_name", "") or "")
        node.resume_named_session_name = str(
            node_state.get("resume_named_session_name", "") or ""
        )
        self._named_sessions = clone_named_sessions(named_sessions)
        self.reconcile_named_sessions()
        self.notify_node_changed(node_id)

    def configure_named_session_for_node(
        self: "WorkflowCanvas",
        node_id: str,
        *,
        save_enabled: bool | None = None,
        save_name: str | None = None,
        resume_name: str | None = None,
        model_id: str | None = None,
    ) -> None:
        next_state, next_named_sessions = self.build_named_session_update(
            node_id,
            save_enabled=save_enabled,
            save_name=save_name,
            resume_name=resume_name,
            model_id=model_id,
        )
        self.apply_named_session_update(node_id, next_state, next_named_sessions)

    def reconcile_named_sessions(self: "WorkflowCanvas") -> None:
        valid_node_ids = set(self._nodes)
        changed_node_ids: set[str] = set()

        for session_name, record in list(self._named_sessions.items()):
            owner_node_id = record.get("owner_node_id", "").strip()
            if owner_node_id not in valid_node_ids:
                self._named_sessions.pop(session_name, None)
                continue
            owner = self._nodes.get(owner_node_id)
            if not isinstance(owner, LLMNode):
                self._named_sessions.pop(session_name, None)
                continue
            provider = get_provider_for_model(owner.model_id or "")
            supports_resume = bool(
                provider is not None and provider.supports_session_resume(owner.model_id)
            )
            if not supports_resume or not owner.save_session_enabled:
                self._named_sessions.pop(session_name, None)
                changed_node_ids.add(owner_node_id)
                continue
            provider_name = provider.name
            if session_name != normalize_session_name(owner.save_session_name):
                self._named_sessions.pop(session_name, None)
                continue
            if record.get("provider", "").strip() != provider_name:
                record["provider"] = provider_name
                record["session_id"] = ""

        for node in self._nodes.values():
            if not isinstance(node, LLMNode):
                continue
            provider = get_provider_for_model(node.model_id or "")
            supports_resume = bool(
                provider is not None and provider.supports_session_resume(node.model_id)
            )
            if not supports_resume:
                if (
                    node.resume_session_enabled
                    or node.save_session_enabled
                    or node.save_session_name
                    or node.resume_named_session_name
                ):
                    node.resume_session_enabled = False
                    node.save_session_enabled = False
                    node.save_session_name = ""
                    node.resume_named_session_name = ""
                    changed_node_ids.add(node.node_id)
                continue
            provider_name = provider.name
            if node.save_session_enabled and node.save_session_name:
                session_name = normalize_session_name(node.save_session_name)
                record = self._named_sessions.get(session_name)
                if record is None or record.get("owner_node_id") != node.node_id:
                    node.save_session_enabled = False
                    changed_node_ids.add(node.node_id)
            if node.resume_named_session_name and not named_session_is_available(
                self._named_sessions,
                self._connections,
                session_name=node.resume_named_session_name,
                provider_name=provider_name,
                target_node_id=node.node_id,
            ):
                node.resume_named_session_name = ""
                changed_node_ids.add(node.node_id)

        if changed_node_ids:
            selected_ids = {item.node_id for item in self.selected_workflow_nodes()}
            if selected_ids.intersection(changed_node_ids):
                self.selection_changed.emit()
