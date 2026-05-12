# llm_sessions Developer Guide

## Purpose
`llm_sessions/` isolates workflow-level LLM session helpers so `main_window.py` and `properties_panel.py` stay under the file-size cap while the named-session feature remains easy to reason about.

## Files
- `session_state.py`: Normalizes workflow JSON named-session records, clones/clears the in-memory store, answers provider/path-based availability checks for the resume dropdown, and reconciles the save-owner restart flag with provider support and save ownership.
- `panel_helpers.py`: Loads the LLM form state for `PropertiesPanel` and keeps prompt-preview, per-node prompt-template dropdowns, variable-warning notes, and session-control widgets in sync with the selected node.
- `main_window_handlers.py`: Holds the `MainWindow` handlers for model changes plus named-session save/resume/restart edits so the window class stays under the file-size cap.
- `overview.py`: Builds the workflow-overview and connection-overview text shown in the always-visible properties panel.

## Named Session Rules
- Named sessions are workflow-level records keyed by a user-defined name and stored in workflow JSON under `named_sessions`.
- Each record stores `owner_node_id`, `provider`, and the captured `session_id`.
- Only the save-owner node may reserve a given name.
- The save-owner node may also persist a restart flag. That flag makes the owner node start fresh for its own execution while leaving the currently saved workflow session available to other branches until the owner finishes and overwrites it.
- Resume options only include named sessions that already have a real `session_id`, match the selected node's provider, and have a directed graph path from the save-owner node to the current load node.
- If graph edits, provider changes, or owner-node removal make a named-session reference invalid, the owning canvas code clears the stale resume selection.
- When extending prompt-preview behavior, keep variable resolution delegated to shared canvas-side analysis so preview rules stay consistent with run validation and execution-time substitution.
