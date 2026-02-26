# src Developer Guide

## Purpose
`src/` is the runtime package for GUI Workflow. It contains all app code grouped by UI, provider integration, and background execution.

## Folder Map
- `gui/`: Qt graphics-based workflow editor and main window shell.
- `llm/`: Provider abstraction and concrete CLI adapters (Claude, Codex, Gemini).
- `workers/`: Threaded subprocess worker used to execute provider calls without blocking UI.
- `__init__.py`: Package marker.

## Data Flow
1. UI collects node prompts and model selections (with provider logos loaded from `gui/assets/` in a compact model-picker that opens a bounded overlay dropdown on the canvas viewport).
2. `WorkflowCanvas` handles graph interaction including node/edge editing, wheel-to-zoom, right-drag panning, left-drag rubber-band multi-selection, a zoom-stable dot grid background, auto-expanding scene bounds so moved nodes stay reachable, obstacle-aware connection routing around bubble boxes (including an immediate reroute after a new connection is created), and temporary zoom suspension while model dropdowns are open (wheel then scrolls the dropdown list). Bubble ports are direction-cued with ingress/egress arrows that protrude from the node edges and hide when the corresponding side is connected, selected bubbles render a light-blue neon frame for active-state visibility, and connections expose a larger hit area to make arrow selection reliable.
3. Canvas offers three run modes: Run All (trigger-driven from Start node, only reachable nodes, upfront validation), Run Selected (fires selected nodes only, no fan-out to children), and Run From Here (fires selected node and all its descendants). Pre-run validation rejects any node with a missing prompt or model before execution begins.
4. `LLMWorker` runs the provider command in a background `QThread`.
5. Streamed output lines are appended live into each concurrently-running node.

## Current Built-In Models
- Claude provider: Opus 4.6, Sonnet 4.6, Haiku 4.5.
- Codex provider: GPT-5.3 Codex with `low`, default (medium), `high`, and `xhigh` effort options.
- Gemini provider: models declared in `llm/gemini_provider.py`.

## When To Edit What
- Graph interaction/serialization behavior: `gui/`.
- Add or adjust model catalogs and CLI flags: `llm/`.
- Process execution, cancellation, and timeout handling: `workers/`.
