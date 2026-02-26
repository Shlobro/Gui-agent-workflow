# gui Developer Guide

## Purpose
Implements the interactive Qt UI for composing and running LLM workflows.

## Contents
- `main_window.py`: Main shell (toolbar, status bar, save/load/clear actions) and `WorkflowCanvas` host.
- `canvas.py`: `QGraphicsView` orchestration, pan/zoom controls, connection creation, trigger-driven run execution with permanent Start node, pre-run validation, draw-time graph warnings, and workflow save/load serialization.
- `bubble_node.py`: `BubbleNode` — draggable node with embedded editor, model selector, and output panel. `StartNode` — permanent pure-trigger root node with output port only.
- `connection_item.py`: Directed Bezier edge between bubble ports.
- `assets/`: Static logo files used by the model selector.
- `__init__.py`: Package marker.

## Key Interactions
- `WorkflowCanvas` owns node/edge lifecycle and triggers trigger-driven execution: for **Run All**, the permanent `StartNode` is the single root — its direct children fire first, and each node fires its own direct children on successful completion, each invocation in its own `LLMWorker` (exec_id-tagged); cycles run until `stop_all()` is called. Run Selected and Run From Here bypass the Start node and use the selection as the entry point instead.
- Before any run, all reachable nodes are validated: a node with an empty prompt or no model selected blocks the run with a warning dialog listing every problem.
- `WorkflowCanvas` creates `LLMWorker` instances and routes streamed output into the corresponding `BubbleNode`.
- `BubbleNode` holds user-editable metadata (title, prompt, model) used by execution and save/load.
- `MainWindow` delegates all graph behavior to the canvas and focuses on app-level controls.

## Behavior Notes
- The Start node is permanent: it cannot be deleted with the Delete key and is recreated after Clear Canvas. Its position is saved and restored with the workflow JSON.
- Cyclic graphs execute continuously: each node triggers its children on successful completion, so A→B→A loops until the user stops the workflow. Drawing a connection that would create a cycle shows a warning dialog at draw time, but the user may proceed and add it anyway.
- Nodes not reachable from Start are never executed by Run All.
- Children fire only on successful completion; an error node is a dead end and does not trigger its descendants.
- Drawing a second outgoing connection from a node that already has one shows an informational dialog explaining that the node will fan out to multiple parallel children; the user may proceed.
- Three run modes are available: **Run All** executes all nodes reachable from the permanent Start node (requires at least one connection from Start); **Run Selected** fires only the currently selected node(s) simultaneously without triggering their children; **Run From Here** fires the single selected node and all its descendants reachable from it. The Start-root restriction (reachability check and upfront validation) applies only to Run All; the other two modes validate only the nodes they will execute.
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
