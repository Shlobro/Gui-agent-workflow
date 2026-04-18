"""Variable analysis and runtime helpers for WorkflowCanvas."""

from __future__ import annotations

import re
from collections import deque
from typing import TYPE_CHECKING, Dict, Iterable

from src.gui.llm_node import LLMNode, WorkflowNode
from src.gui.variables import (
    VARIABLE_TYPE_NUMBER,
    VariableNode,
    is_valid_number_value,
    is_valid_variable_name,
)

if TYPE_CHECKING:
    from src.gui.canvas import WorkflowCanvas

_PROMPT_VARIABLE_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_AMBIGUOUS_VALUE = object()
GraphState = Dict[str, frozenset[str]]
RuntimeState = Dict[str, object]


def _copy_runtime_state(state: RuntimeState | None) -> RuntimeState:
    return dict(state or {})


def _merge_graph_states(states: Iterable[GraphState]) -> GraphState:
    merged: dict[str, set[str]] = {}
    for state in states:
        for name, values in state.items():
            merged.setdefault(name, set()).update(values)
    return {name: frozenset(values) for name, values in merged.items()}


def _merge_runtime_states(states: Iterable[RuntimeState]) -> RuntimeState:
    merged: RuntimeState = {}
    for state in states:
        for name, value in state.items():
            if name not in merged:
                merged[name] = value
                continue
            if merged[name] is _AMBIGUOUS_VALUE or value is _AMBIGUOUS_VALUE:
                merged[name] = _AMBIGUOUS_VALUE
            elif merged[name] != value:
                merged[name] = _AMBIGUOUS_VALUE
    return merged


class _VariableMixin:
    @staticmethod
    def prompt_variable_names(prompt_text: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for match in _PROMPT_VARIABLE_RE.finditer(prompt_text or ""):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def _clear_variable_runtime_state(self: "WorkflowCanvas") -> None:
        self._lineage_variables.clear()
        self._join_wait_variable_states.clear()

    def _set_lineage_variables(self: "WorkflowCanvas", lineage_token: str, state: RuntimeState) -> None:
        if not lineage_token:
            raise RuntimeError("Variable lineage state requires a non-empty lineage token.")
        self._lineage_variables[lineage_token] = dict(state)

    def _copy_lineage_variables(self: "WorkflowCanvas", source_lineage: str, target_lineage: str) -> None:
        if not target_lineage:
            return
        self._lineage_variables[target_lineage] = _copy_runtime_state(
            self._lineage_variables.get(source_lineage)
        )

    def _apply_variable_node_runtime(
        self: "WorkflowCanvas", node: VariableNode, lineage_token: str
    ) -> str:
        if not lineage_token:
            raise RuntimeError("Variable execution requires a non-empty lineage token.")
        state = _copy_runtime_state(self._lineage_variables.get(lineage_token))
        state[node.variable_name.strip()] = node.variable_value
        self._set_lineage_variables(lineage_token, state)
        return f"Set ${node.variable_name.strip()} = {node.variable_value}"

    def _record_join_variable_state(
        self: "WorkflowCanvas", node_id: str, group_key: str, lineage_token: str
    ) -> None:
        join_key = (node_id, group_key)
        self._join_wait_variable_states.setdefault(join_key, []).append(
            _copy_runtime_state(self._lineage_variables.get(lineage_token))
        )

    def _release_join_variable_state(
        self: "WorkflowCanvas",
        node_id: str,
        group_key: str,
        wait_for_count: int,
        released_lineage: str,
    ) -> None:
        join_key = (node_id, group_key)
        states = self._join_wait_variable_states.get(join_key, [])
        consumed_count = min(wait_for_count, len(states))
        released = _merge_runtime_states(states[:consumed_count])
        remainder = states[consumed_count:]
        if remainder:
            self._join_wait_variable_states[join_key] = remainder
        else:
            self._join_wait_variable_states.pop(join_key, None)
        self._set_lineage_variables(released_lineage, released)

    def _clear_join_variable_state_for_node(self: "WorkflowCanvas", node_id: str) -> None:
        for key in list(self._join_wait_variable_states):
            if key[0] == node_id:
                self._join_wait_variable_states.pop(key, None)

    def _variable_graph_states(
        self: "WorkflowCanvas", allowed_node_ids: set[str] | None = None
    ) -> tuple[dict[str, GraphState], dict[str, GraphState]]:
        node_ids = [
            node.node_id
            for node in self.workflow_nodes()
            if allowed_node_ids is None or node.node_id in allowed_node_ids
        ]
        input_states: dict[str, GraphState] = {node_id: {} for node_id in node_ids}
        output_states: dict[str, GraphState] = {node_id: {} for node_id in node_ids}
        queue = deque(node_ids)
        queued = set(node_ids)
        while queue:
            node_id = queue.popleft()
            queued.discard(node_id)
            node = self._nodes.get(node_id)
            if node is None:
                continue
            incoming = [
                output_states.get(conn.source_node.node_id, {})
                for conn in self._connections
                if conn.target_node is node
                and (allowed_node_ids is None or conn.source_node.node_id in allowed_node_ids)
            ]
            merged_input = _merge_graph_states(incoming)
            next_output = dict(merged_input)
            if isinstance(node, VariableNode) and is_valid_variable_name(node.variable_name):
                next_output[node.variable_name.strip()] = frozenset({node.variable_value})
            if merged_input != input_states.get(node_id) or next_output != output_states.get(node_id):
                input_states[node_id] = merged_input
                output_states[node_id] = next_output
                for conn in self._connections:
                    if conn.source_node is node and (
                        allowed_node_ids is None or conn.target_node.node_id in allowed_node_ids
                    ):
                        target_id = conn.target_node.node_id
                        if target_id not in queued:
                            queue.append(target_id)
                            queued.add(target_id)
        return input_states, output_states

    def llm_prompt_variable_issues(
        self: "WorkflowCanvas",
        node: LLMNode,
        prompt_text: str | None = None,
        allowed_node_ids: set[str] | None = None,
    ) -> tuple[dict[str, str], list[str], list[str]]:
        input_states, _ = self._variable_graph_states(allowed_node_ids=allowed_node_ids)
        state = input_states.get(node.node_id, {})
        resolved: dict[str, str] = {}
        errors: list[str] = []
        warnings: list[str] = []
        for name in self.prompt_variable_names(node.prompt_text if prompt_text is None else prompt_text):
            values = state.get(name)
            if not values:
                errors.append(f'references ${name}, but no reachable upstream variable defines it')
            elif len(values) > 1:
                warnings.append(f'${name} is ambiguous because multiple upstream values can reach this node')
            else:
                resolved[name] = next(iter(values))
        return resolved, errors, warnings

    def llm_variable_validation_errors(
        self: "WorkflowCanvas", node: LLMNode, allowed_node_ids: set[str] | None = None
    ) -> list[str]:
        _resolved, errors, _warnings = self.llm_prompt_variable_issues(
            node,
            allowed_node_ids=allowed_node_ids,
        )
        return errors

    def render_llm_prompt_text(
        self: "WorkflowCanvas",
        node: LLMNode,
        prompt_text: str | None = None,
        lineage_token: str = "",
    ) -> tuple[str, list[str]]:
        text = node.prompt_text if prompt_text is None else prompt_text
        if not lineage_token:
            resolved, errors, warnings = self.llm_prompt_variable_issues(node, text)
            rendered = _PROMPT_VARIABLE_RE.sub(lambda m: resolved.get(m.group(1), m.group(0)), text)
            return rendered, [*errors, *warnings]

        state = self._lineage_variables.get(lineage_token, {})
        warnings: list[str] = []

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            value = state.get(name)
            if value is _AMBIGUOUS_VALUE:
                warnings.append(f'${name} is ambiguous at runtime and was left unchanged')
                return match.group(0)
            if value is None:
                return match.group(0)
            return str(value)

        return _PROMPT_VARIABLE_RE.sub(replace, text), warnings

    def variable_node_warning_text(
        self: "WorkflowCanvas",
        node: VariableNode,
        variable_name: str | None = None,
        input_states: dict[str, GraphState] | None = None,
    ) -> str:
        effective_name = (node.variable_name if variable_name is None else variable_name).strip()
        if not is_valid_variable_name(effective_name):
            return ""
        if input_states is None:
            input_states, _ = self._variable_graph_states()
        if effective_name in input_states.get(node.node_id, {}):
            return (
                f'This node overwrites an upstream ${effective_name} definition '
                "for every downstream path that passes through it."
            )
        return ""

    def variable_node_warning_text_for_preview(
        self: "WorkflowCanvas", node: VariableNode, preview_name: str | None = None
    ) -> str:
        input_states, _ = self._variable_graph_states()
        return self.variable_node_warning_text(
            node,
            variable_name=preview_name,
            input_states=input_states,
        )

    def variable_validation_errors(self: "WorkflowCanvas", node: VariableNode) -> list[str]:
        reasons: list[str] = []
        if not node.variable_name.strip():
            reasons.append("has no variable name")
        elif not is_valid_variable_name(node.variable_name):
            reasons.append("uses an invalid variable name")
        if node.variable_type not in {"text", VARIABLE_TYPE_NUMBER}:
            reasons.append(f'has unknown variable type "{node.variable_type}"')
        if node.variable_type == VARIABLE_TYPE_NUMBER and not is_valid_number_value(node.variable_value):
            reasons.append("has a value that is not a valid number")
        return reasons

    def _fire_variable_node(
        self: "WorkflowCanvas",
        node: VariableNode,
        exec_id: int,
        lineage_token: str = "",
        loop_token: str = "",
        join_token: str = "",
    ) -> None:
        self._on_invocation_done(
            node,
            exec_id,
            self._apply_variable_node_runtime(node, lineage_token),
            error=False,
            run_id=self._run_id,
            lineage_token=lineage_token,
            loop_token=loop_token,
            join_token=join_token,
        )
