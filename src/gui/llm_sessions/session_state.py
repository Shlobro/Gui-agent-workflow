"""Helpers for workflow-level named LLM session state."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any


def normalize_session_name(name: str) -> str:
    return str(name or "").strip()


def clone_named_sessions(named_sessions: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    return deepcopy(named_sessions)


def parse_named_sessions(data: Any) -> dict[str, dict[str, str]]:
    if data is None:
        return {}
    if not isinstance(data, list):
        raise ValueError("Field 'named_sessions' must be an array.")

    parsed: dict[str, dict[str, str]] = {}
    for idx, raw in enumerate(data):
        if not isinstance(raw, dict):
            raise ValueError(f"Named session record at index {idx} is not an object.")
        name = normalize_session_name(raw.get("name", ""))
        if not name:
            raise ValueError(f"Named session record at index {idx} is missing 'name'.")
        if name in parsed:
            raise ValueError(f"Duplicate named session '{name}'.")

        owner_node_id = raw.get("owner_node_id", "")
        provider = raw.get("provider", "")
        session_id = raw.get("session_id", "")
        for field_name, value in (
            ("owner_node_id", owner_node_id),
            ("provider", provider),
            ("session_id", session_id),
        ):
            if not isinstance(value, str):
                raise ValueError(
                    f"Named session '{name}' has non-string '{field_name}'."
                )

        parsed[name] = {
            "owner_node_id": owner_node_id.strip(),
            "provider": provider.strip(),
            "session_id": session_id.strip(),
        }
    return parsed


def build_named_sessions_payload(
    named_sessions: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for name in sorted(named_sessions, key=str.casefold):
        record = named_sessions[name]
        payload.append(
            {
                "name": name,
                "owner_node_id": record.get("owner_node_id", "").strip(),
                "provider": record.get("provider", "").strip(),
                "session_id": record.get("session_id", "").strip(),
            }
        )
    return payload


def clear_named_session_ids(named_sessions: dict[str, dict[str, str]]) -> None:
    for record in named_sessions.values():
        record["session_id"] = ""


def count_saved_named_sessions(named_sessions: dict[str, dict[str, str]]) -> int:
    return sum(1 for record in named_sessions.values() if record.get("session_id", "").strip())


def has_connection_path(connections: list[Any], source_id: str, target_id: str) -> bool:
    source_id = (source_id or "").strip()
    target_id = (target_id or "").strip()
    if not source_id or not target_id or source_id == target_id:
        return False

    adjacency: dict[str, set[str]] = {}
    for connection in connections:
        if isinstance(connection, dict):
            src_id = str(connection.get("from", "")).strip()
            tgt_id = str(connection.get("to", "")).strip()
        else:
            src_id = str(getattr(getattr(connection, "source_node", None), "node_id", "")).strip()
            tgt_id = str(getattr(getattr(connection, "target_node", None), "node_id", "")).strip()
        if not src_id or not tgt_id:
            continue
        adjacency.setdefault(src_id, set()).add(tgt_id)

    queue = deque([source_id])
    visited = {source_id}
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor == target_id:
                return True
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append(neighbor)
    return False


def named_session_is_available(
    named_sessions: dict[str, dict[str, str]],
    connections: list[Any],
    *,
    session_name: str,
    provider_name: str,
    target_node_id: str,
) -> bool:
    name = normalize_session_name(session_name)
    if not name:
        return False
    record = named_sessions.get(name)
    if record is None:
        return False
    if record.get("provider", "").strip() != provider_name.strip():
        return False
    return has_connection_path(
        connections,
        record.get("owner_node_id", ""),
        target_node_id,
    )


def available_named_session_options(
    named_sessions: dict[str, dict[str, str]],
    connections: list[Any],
    *,
    provider_name: str,
    target_node_id: str,
) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    for name in sorted(named_sessions, key=str.casefold):
        record = named_sessions.get(name)
        if record is None:
            continue
        if record.get("provider", "").strip() != provider_name.strip():
            continue
        if not has_connection_path(
            connections,
            record.get("owner_node_id", ""),
            target_node_id,
        ):
            continue
        options.append((name, name))
    return options
