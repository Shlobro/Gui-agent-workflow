# gui Developer Guide

## Purpose
Implements the interactive Qt UI for composing and running LLM workflows.

## Contents
- `main_window.py`: Main shell (toolbar, status bar, save/load/clear actions) and `WorkflowCanvas` host.
- `canvas.py`: `QGraphicsView` orchestration, pan/zoom controls, connection creation, run sequencing, and workflow save/load serialization.
- `bubble_node.py`: Node rendering, embedded widget editor, compact provider-logo model selector with top-level overlay dropdown, port positions, status color, and per-node output panel.
- `connection_item.py`: Directed Bezier edge between bubble ports.
- `assets/`: Static logo files used by the model selector.
- `__init__.py`: Package marker.

## Key Interactions
- `WorkflowCanvas` owns node/edge lifecycle and triggers sequential execution.
- `WorkflowCanvas` creates `LLMWorker` instances and routes streamed output into the active `BubbleNode`.
- `BubbleNode` holds user-editable metadata (title, prompt, model) used by execution and save/load.
- `MainWindow` delegates all graph behavior to the canvas and focuses on app-level controls.

## Behavior Notes
- Only acyclic subgraphs are executable; cycles are blocked with an error dialog.
- Running from selection executes the reachable subgraph from that node.
- Mouse wheel zoom is active on the canvas (zoom under cursor) with zoom clamped to prevent extreme scales, except while a model dropdown is open where wheel input scrolls the dropdown list instead of zooming.
- Canvas panning is driven by right-button drag (middle-button drag remains accepted).
- Left-drag on empty canvas uses a rubber-band rectangle to select multiple bubbles at once.
- Background grid dots are rendered with a cosmetic pen so they stay visible and keep a fixed on-screen size across zoom levels.
- Scene bounds auto-expand around moved/loaded nodes with padding so corner nodes remain reachable after zooming and panning.
- Connection paths are routed around bubble bounding boxes using obstacle-aware grid routing; route recompute runs immediately after connection creation and whenever bubbles move/resize so lines avoid passing under bubbles.
- Arrowheads terminate just outside the target input port, keeping direction visible instead of being hidden by the port dot.
- Bubble ports are direction-cued and color-differentiated: a left-side ingress arrow and right-side egress arrow protrude from the bubble edge to indicate flow, and each arrow hides once that side has at least one connection.
- Connection items use an expanded hit-test shape (line + arrowhead) so selecting arrows for delete is easier without rendering thicker lines.
- Selected bubbles render an additional light-blue neon frame so active selection is visually obvious.
- Connections only define execution order; node outputs are displayed per node and are not injected into downstream prompts.
- Model selection uses a compact selector row that opens an overlay dropdown on the canvas viewport (not a Qt popup window), keeps node height unchanged while open, anchors dropdown position from scene coordinates so it stays aligned with moved/zoomed nodes, clamps geometry to visible viewport bounds (opening upward when needed), shows provider logos from `assets/` (Anthropic/OpenAI/Gemini), normalizes them to a 16x16 icon canvas, auto-selects the first available model, and lazy-loads provider modules if needed.
