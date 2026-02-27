"""Workflow serialization, payload validation, and provider-lookup helpers.

Pure functions that convert between the canvas scene state and the JSON-
serialisable dict format used for save/load, plus the provider registry lookup
used by both canvas execution and validation.  No Qt widget state is mutated
here; callers are responsible for applying the returned data to the scene.
"""

from typing import List

from src.llm.base_provider import LLMProviderRegistry
from .llm_node import LLMNode
from .file_op_node import NODE_TYPE_MAP


def get_provider_for_model(model_id: str):
    """Return the first registered provider that exposes model_id, or None."""
    for provider in LLMProviderRegistry.all():
        for mid, _ in provider.get_models():
            if mid == model_id:
                return provider
    return None


def parse_workflow_data(data: dict) -> dict:
    """Validate and normalise a raw workflow payload.

    Raises ValueError on any structural problem with top-level fields or node
    records.  Malformed connection records are silently dropped because a
    partial connection set is still a coherent graph.

    Returns a normalised dict with keys:
        node_counter, start_pos, nodes, connections
    """
    if not isinstance(data, dict):
        raise ValueError("Workflow JSON root must be an object.")

    node_counter = data.get("node_counter", 0)
    if not isinstance(node_counter, int):
        raise ValueError("Field 'node_counter' must be an integer.")

    start_pos = data.get("start_pos")
    if start_pos is not None:
        if not isinstance(start_pos, (list, tuple)) or len(start_pos) < 2:
            raise ValueError("Field 'start_pos' must be a 2-item array.")
        x, y = start_pos[0], start_pos[1]
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError("Field 'start_pos' coordinates must be numbers.")
        normalized_start_pos = (x, y)
    else:
        normalized_start_pos = None

    nodes_data = data.get("nodes", [])
    if not isinstance(nodes_data, list):
        raise ValueError("Field 'nodes' must be an array.")

    normalized_nodes: List[dict] = []
    node_ids: set[str] = set()
    max_label_index = 0
    for idx_in_list, b_data in enumerate(nodes_data):
        if not isinstance(b_data, dict):
            raise ValueError(f"Node record at index {idx_in_list} is not an object.")

        label_index = b_data.get("label_index", 1)
        if not isinstance(label_index, int):
            label_index = 1

        node_type = b_data.get("node_type", "llm")
        if not isinstance(node_type, str):
            raise ValueError(f"Node record at index {idx_in_list} has invalid 'node_type' (must be a string).")

        # Validate raw string fields before from_dict so falsey non-strings
        # (0, false, [], null) are caught rather than silently collapsed to "".
        for str_field in ("name", "model", "prompt", "filename"):
            if str_field in b_data and not isinstance(b_data[str_field], str):
                raise ValueError(
                    f"Node record at index {idx_in_list} has non-string '{str_field}'."
                )

        node_cls = NODE_TYPE_MAP.get(node_type, LLMNode)
        temp_node = node_cls(node_id=b_data.get("id"), label_index=label_index)
        try:
            temp_node.from_dict(b_data)
        except Exception as e:
            raise ValueError(f"Invalid node record at index {idx_in_list}: {e}") from e

        snapshot = temp_node.to_dict()
        # Coerce label_index to int in case from_dict overwrote it with a
        # non-integer from the raw dict.
        snapshot["label_index"] = label_index

        node_id = snapshot.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError(f"Node record at index {idx_in_list} has a missing or invalid 'id'.")
        if node_id in node_ids:
            raise ValueError(f"Duplicate node id '{node_id}' at index {idx_in_list}.")
        node_ids.add(node_id)
        max_label_index = max(max_label_index, label_index)
        normalized_nodes.append(snapshot)

    node_counter = max(node_counter, max_label_index)

    connections_data = data.get("connections", [])
    if not isinstance(connections_data, list):
        raise ValueError("Field 'connections' must be an array.")

    normalized_connections: List[dict] = []
    for c_data in connections_data:
        if not isinstance(c_data, dict):
            continue
        src_id = c_data.get("from")
        tgt_id = c_data.get("to")
        if not isinstance(src_id, str) or not isinstance(tgt_id, str):
            continue
        if tgt_id == "start":
            continue  # Start has no input port; skip invalid edges
        if src_id != "start" and src_id not in node_ids:
            continue
        if tgt_id not in node_ids:
            continue
        normalized_connections.append({"from": src_id, "to": tgt_id})

    return {
        "node_counter": node_counter,
        "start_pos": normalized_start_pos,
        "nodes": normalized_nodes,
        "connections": normalized_connections,
    }


def build_workflow_data(nodes, connections, node_counter: int, start_node) -> dict:
    """Serialise the current canvas state to a JSON-serialisable dict."""
    sp = start_node.pos()
    return {
        "nodes": [n.to_dict() for n in nodes],
        "connections": [c.to_dict() for c in connections],
        "node_counter": node_counter,
        "start_pos": [sp.x(), sp.y()],
    }
