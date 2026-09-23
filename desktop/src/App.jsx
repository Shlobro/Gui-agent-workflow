import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import {
  AlertCircle,
  CirclePlay,
  FolderOpen,
  GitBranch,
  LayoutGrid,
  MoreHorizontal,
  Plus,
  RotateCcw,
  RotateCw,
  Save,
  Search,
  Square,
  Trash2,
  Workflow,
} from "lucide-react";
import GraphNode, { nodeKinds } from "./GraphNode.jsx";
import WorkflowEdge from "./WorkflowEdge.jsx";
import Inspector from "./Inspector.jsx";
import {
  AttentionDialog,
  SessionDialog,
  TemplatesDialog,
  UsageDialog,
} from "./Dialogs.jsx";

const nodeTypes = { workflow: GraphNode };
const edgeTypes = { workflow: WorkflowEdge };
const palette = [
  "llm",
  "create_file",
  "variable",
  "conditional",
  "loop",
  "join",
  "git_action",
  "script_runner",
  "attention",
];

function edgeId(connection) {
  return `${connection.from}:${connection.source_port || "output"}:${connection.to}`;
}

function Editor() {
  const [state, setState] = useState({
    nodes: [],
    connections: [],
    start_pos: [0, 0],
    models: [],
    status: "Starting runtime...",
  });
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [toast, setToast] = useState(null);
  const [showMore, setShowMore] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [pendingRun, setPendingRun] = useState(null);
  const [attention, setAttention] = useState(null);
  const [usage, setUsage] = useState(null);
  const dragging = useRef(false);
  const fittedPath = useRef(undefined);
  const currentState = useRef(state);
  const rf = useReactFlow();
  currentState.current = state;

  const notify = useCallback((message, tone = "error") => {
    setToast({ message, tone, key: Date.now() });
    setTimeout(
      () =>
        setToast((current) => (current?.message === message ? null : current)),
      6000,
    );
  }, []);

  const request = useCallback(
    async (action, payload = {}) => {
      try {
        return await window.workflow.request(action, payload);
      } catch (error) {
        notify(error.message);
        return null;
      }
    },
    [notify],
  );

  useEffect(() => {
    const unsubscribe = window.workflow.onMessage((message) => {
      if (message.type === "state") {
        setState(message.state);
        if (!message.state.running) setAttention(null);
      }
      if (message.type === "error") notify(message.error);
      if (message.type === "usage_limit") setUsage(message);
      if (message.type === "attention") setAttention(message);
    });
    window.workflow
      .request("state")
      .then(setState)
      .catch((error) => notify(error.message));
    return unsubscribe;
  }, [notify]);

  useEffect(() => {
    if (dragging.current) return;
    const records = [
      {
        id: "start",
        node_type: "start",
        name: "Start",
        x: state.start_pos?.[0] || 0,
        y: state.start_pos?.[1] || 0,
      },
      ...(state.nodes || []),
    ];
    setNodes(
      records.map((node) => ({
        id: node.id,
        type: "workflow",
        position: { x: node.x, y: node.y },
        data: { node },
        selected: selectedIds.includes(node.id),
        draggable: !state.running,
      })),
    );
    setEdges(
      (state.connections || []).map((connection) => ({
        id: edgeId(connection),
        source: connection.from,
        target: connection.to,
        sourceHandle: connection.source_port || "output",
        targetHandle: "input",
        type: "workflow",
        animated: state.running,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#8193b5",
          width: 18,
          height: 18,
        },
        style: { stroke: "#717b94", strokeWidth: 2 },
        selected: selectedEdge?.id === edgeId(connection),
        data: {
          connection,
          onVertices: (vertices) =>
            request("set_vertices", { ...connection, vertices }),
          onSelect: () => {
            setSelectedIds([]);
            setSelectedEdge(connection);
          },
        },
      })),
    );
  }, [state, selectedIds, selectedEdge, setNodes, setEdges, request]);

  useEffect(() => {
    if (fittedPath.current === state.workflow_path) return;
    fittedPath.current = state.workflow_path;
    const timer = setTimeout(async () => {
      await rf.fitView({ padding: 0.28, duration: 350, maxZoom: 1.25 });
      if (rf.getZoom() < 0.5) rf.zoomTo(0.55, { duration: 250 });
    }, 250);
    return () => clearTimeout(timer);
  }, [rf, state.workflow_path]);

  const chosen = state.nodes?.find((node) => node.id === selectedIds[0]);
  const selectedCount = selectedIds.filter((id) => id !== "start").length;
  const projectName =
    state.project_folder?.split(/[\\/]/).filter(Boolean).at(-1) ||
    "No project selected";

  const choose = useCallback(
    async (kind) => {
      try {
        if (
          kind === "load" &&
          currentState.current.dirty &&
          !window.confirm("Discard unsaved workflow changes?")
        )
          return;
        const path = await window.workflow.dialog(kind, {
          current: currentState.current.workflow_path,
          project: currentState.current.project_folder,
        });
        if (path)
          await request(kind === "project" ? "project" : kind, { path });
      } catch (error) {
        notify(error.message);
      }
    },
    [notify, request],
  );

  const save = useCallback(
    async (as = false) => {
      const path =
        !as && currentState.current.workflow_path
          ? currentState.current.workflow_path
          : await window.workflow.dialog("save", {
              current: currentState.current.workflow_path,
            });
      if (path) await request("save", { path });
    },
    [request],
  );

  const addNode = useCallback(
    (nodeType) => {
      const point = rf.screenToFlowPosition({
        x: window.innerWidth * 0.52,
        y: window.innerHeight * 0.5,
      });
      request("add_node", { node_type: nodeType, x: point.x, y: point.y });
    },
    [request, rf],
  );

  const removeSelection = useCallback(async () => {
    if (currentState.current.running) return;
    if (selectedEdge) {
      await request("delete_connection", selectedEdge);
      setSelectedEdge(null);
    }
    for (const id of selectedIds)
      if (id !== "start") await request("delete_node", { id });
    setSelectedIds([]);
  }, [request, selectedEdge, selectedIds]);

  useEffect(() => {
    const onKeyDown = (event) => {
      const editing = ["INPUT", "TEXTAREA", "SELECT"].includes(
        document.activeElement?.tagName,
      );
      if (editing) return;
      const control = event.ctrlKey || event.metaKey;
      if (control && event.key.toLowerCase() === "s") {
        event.preventDefault();
        save(event.shiftKey);
      }
      if (control && event.key.toLowerCase() === "o") {
        event.preventDefault();
        choose("load");
      }
      if (control && event.key.toLowerCase() === "z") {
        event.preventDefault();
        request(event.shiftKey ? "redo" : "undo");
      }
      if (control && event.key.toLowerCase() === "y") {
        event.preventDefault();
        request("redo");
      }
      if (control && event.key.toLowerCase() === "c") {
        event.preventDefault();
        request("copy", { ids: selectedIds.filter((id) => id !== "start") });
      }
      if (control && event.key.toLowerCase() === "v") {
        event.preventDefault();
        request("paste");
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        removeSelection();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [choose, removeSelection, request, save]);

  const onConnect = useCallback(
    async (params) => {
      const payload = {
        from: params.source,
        to: params.target,
        source_port: params.sourceHandle || "output",
      };
      try {
        await window.workflow.request("connect", payload);
      } catch (error) {
        if (
          error.message.startsWith("Cycle warning:") &&
          window.confirm(
            "This connection creates a cycle. The nodes may run repeatedly until you stop the workflow. Add it?",
          )
        ) {
          request("connect", { ...payload, confirmed_cycle: true });
        } else if (!error.message.startsWith("Cycle warning:"))
          notify(error.message);
      }
    },
    [notify, request],
  );

  const onNodeDragStop = useCallback(
    (_event, node) => {
      dragging.current = false;
      request("move_node", {
        id: node.id,
        x: node.position.x,
        y: node.position.y,
      });
    },
    [request],
  );

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes, edges: selectedEdges }) => {
      const ids = selectedNodes.map((node) => node.id);
      setSelectedIds((current) =>
        current.length === ids.length &&
        current.every((id, index) => id === ids[index])
          ? current
          : ids,
      );
      const edge = selectedEdges[0]?.data?.connection || null;
      setSelectedEdge((current) =>
        edgeId(current || {}) === edgeId(edge || {}) ? current : edge,
      );
    },
    [],
  );

  const browseScript = useCallback(
    async (id) => {
      const path = await window.workflow.dialog("script", {
        project: currentState.current.project_folder,
      });
      if (!path) return;
      const folder = currentState.current.project_folder;
      if (
        !folder ||
        !["\\", "/"].some((separator) =>
          path
            .toLowerCase()
            .startsWith(folder.toLowerCase().replace(/[\\/]$/, "") + separator),
        )
      ) {
        notify("Choose a script inside the current project folder.");
        return;
      }
      const relative = path
        .slice(folder.length)
        .replace(/^[\\/]/, "")
        .replaceAll("\\", "/");
      request("patch_node", { id, patch: { script_path: relative } });
    },
    [notify, request],
  );

  const beginRun = useCallback(
    (payload) => {
      if (state.saved_sessions_pending) setPendingRun(payload);
      else request("run", payload);
    },
    [request, state.saved_sessions_pending],
  );

  const actions = useMemo(
    () => ({
      runAll: () => beginRun({ mode: "all" }),
      runSelected: () =>
        beginRun({
          mode: "selected",
          ids: selectedIds.filter((id) => id !== "start"),
        }),
      runFrom: () =>
        beginRun({
          mode: "from",
          ids: selectedIds.filter((id) => id !== "start").slice(0, 1),
        }),
    }),
    [beginRun, selectedIds],
  );

  return (
    <div className="app-shell">
      <header className="titlebar">
        <div className="brand">
          <span className="brand-mark">
            <Workflow size={19} />
          </span>
          <div>
            <strong>GUI Workflow</strong>
            <small>Workflow studio</small>
          </div>
        </div>
        <div className="project-pill" title={state.project_folder || ""}>
          <span
            className={
              state.project_folder ? "project-dot active" : "project-dot"
            }
          />
          {projectName}
          <button
            title="Choose project folder"
            onClick={() => choose("project")}
          >
            <FolderOpen size={16} />
          </button>
        </div>
        <div className="titlebar-actions">
          <button className="text-button" onClick={() => choose("load")}>
            <FolderOpen size={16} /> Open
          </button>
          <button className="text-button" onClick={() => save()}>
            <Save size={16} /> Save
          </button>
          <button
            className="icon-button"
            title="More options"
            onClick={() => setShowMore(!showMore)}
          >
            <MoreHorizontal size={20} />
          </button>
          {showMore && (
            <div className="more-menu">
              <button
                onClick={() => {
                  save(true);
                  setShowMore(false);
                }}
              >
                Save as...
              </button>
              <button
                onClick={() => {
                  setShowTemplates(true);
                  setShowMore(false);
                }}
              >
                Prompt templates...
              </button>
              <button
                onClick={() => {
                  choose("project");
                  setShowMore(false);
                }}
              >
                Change project folder
              </button>
              <button
                onClick={() => {
                  request("rescan_models");
                  setShowMore(false);
                }}
              >
                Rescan provider CLIs
              </button>
              <button
                onClick={() => {
                  request("clear_sessions");
                  setShowMore(false);
                }}
              >
                Clear saved sessions
              </button>
              <button
                onClick={() => {
                  if (window.confirm("Clear all nodes and connections?"))
                    request("clear");
                  setShowMore(false);
                }}
              >
                Clear canvas
              </button>
            </div>
          )}
        </div>
      </header>
      <div className="workspace">
        <aside className="library">
          <div className="library-header">
            <div className="eyebrow">BUILD</div>
            <h2>Node library</h2>
            <p>Choose a step to add it to the canvas.</p>
          </div>
          <div className="library-search">
            <Search size={15} />
            <span>Drag and connect nodes</span>
          </div>
          <div className="library-group">STEPS</div>
          <div className="library-list">
            {palette.map((type) => {
              const kind = nodeKinds[type];
              const Icon = kind.Icon;
              return (
                <button
                  key={type}
                  className="library-item"
                  onClick={() => addNode(type)}
                  disabled={state.running}
                >
                  <span className={`library-icon tone-${kind.tone}`}>
                    <Icon size={18} />
                  </span>
                  <span>{kind.label.replaceAll("_", " ")}</span>
                  <Plus size={16} className="library-plus" />
                </button>
              );
            })}
          </div>
          <div className="library-footer">
            <LayoutGrid size={16} />
            <span>{state.nodes.length} nodes on canvas</span>
          </div>
        </aside>
        <main className="canvas-column">
          <div className="commandbar">
            <div className="commandbar-left">
              <span className="eyebrow">CANVAS</span>
              <strong>
                {state.workflow_path?.split(/[\\/]/).at(-1) ||
                  "Untitled workflow"}
                {state.dirty ? " *" : ""}
              </strong>
            </div>
            <div className="commandbar-actions">
              <button
                className="icon-button"
                title="Fit graph"
                onClick={() => rf.fitView({ padding: 0.22, duration: 350 })}
              >
                <LayoutGrid size={17} />
              </button>
              <button
                className="icon-button"
                title="Undo"
                disabled={!state.can_undo || state.running}
                onClick={() => request("undo")}
              >
                <RotateCcw size={17} />
              </button>
              <button
                className="icon-button"
                title="Redo"
                disabled={!state.can_redo || state.running}
                onClick={() => request("redo")}
              >
                <RotateCw size={17} />
              </button>
              <span className="command-divider" />
              <button
                className="run-secondary"
                disabled={state.running || !selectedCount}
                onClick={actions.runSelected}
              >
                Run selected
              </button>
              <button
                className="run-secondary"
                disabled={state.running || selectedCount !== 1}
                onClick={actions.runFrom}
              >
                Run from here
              </button>
              {state.running ? (
                <button className="stop-button" onClick={() => request("stop")}>
                  <Square size={15} fill="currentColor" /> Stop
                </button>
              ) : (
                <button className="run-button" onClick={actions.runAll}>
                  <CirclePlay size={17} /> Run all
                </button>
              )}
            </div>
          </div>
          <div className="canvas-wrap">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStart={() => {
                dragging.current = true;
              }}
              onNodeDragStop={onNodeDragStop}
              onSelectionChange={onSelectionChange}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              fitView
              fitViewOptions={{ padding: 0.25, maxZoom: 1.3 }}
              minZoom={0.2}
              maxZoom={2.5}
              panOnDrag={[1, 2]}
              selectionOnDrag
              multiSelectionKeyCode="Shift"
              deleteKeyCode={null}
              connectionLineStyle={{ stroke: "#88adff", strokeWidth: 2 }}
            >
              <Background color="#283142" gap={24} size={1.25} />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                maskColor="rgba(11, 16, 25, 0.78)"
                nodeStrokeWidth={2}
                nodeColor={(node) =>
                  node.data?.node?.invalid ? "#dd6671" : "#5d87ff"
                }
              />
            </ReactFlow>
            <div className="canvas-hint">
              <GitBranch size={14} /> Connect ports to build your workflow
            </div>
          </div>
          <div className="statusbar">
            <span
              className={state.running ? "status-led active" : "status-led"}
            />
            <span>{state.status}</span>
            <span className="statusbar-spacer" />
            <span>{state.connections.length} connections</span>
          </div>
        </main>
        <Inspector
          node={chosen}
          state={state}
          onPatch={(id, patch) => {
            if (
              patch.model &&
              chosen?.saved_session_id &&
              patch.model !== chosen.model &&
              !window.confirm(
                "Changing this model clears its saved CLI session. Continue?",
              )
            )
              return;
            request("patch_node", { id, patch });
          }}
          onBrowseScript={browseScript}
          onNodeTemplates={(id, side, ids) =>
            request("node_templates", { id, side, ids })
          }
        />
      </div>
      {selectedEdge && (
        <div className="edge-popover">
          <span>
            {selectedEdge.from === "start"
              ? "Start"
              : state.nodes.find((node) => node.id === selectedEdge.from)
                  ?.name}{" "}
            → {state.nodes.find((node) => node.id === selectedEdge.to)?.name}
          </span>
          <button title="Delete connection" onClick={removeSelection}>
            <Trash2 size={16} />
          </button>
        </div>
      )}
      {toast && (
        <div className={`toast ${toast.tone}`} key={toast.key}>
          <AlertCircle size={18} />
          <span>{toast.message}</span>
          <button onClick={() => setToast(null)}>×</button>
        </div>
      )}
      {pendingRun && (
        <SessionDialog
          onChoose={(choice) => {
            if (choice)
              request("run", { ...pendingRun, session_choice: choice });
            setPendingRun(null);
          }}
        />
      )}
      {attention && (
        <AttentionDialog
          request={attention}
          onChoose={(continueRun) => {
            request("attention_response", {
              token: attention.token,
              continue: continueRun,
            });
            setAttention(null);
          }}
        />
      )}
      {usage && (
        <UsageDialog
          event={usage}
          onClose={() => setUsage(null)}
          onChangeModel={() => {
            setSelectedIds([usage.node_id]);
            setUsage(null);
          }}
          onSchedule={(at) => {
            request("schedule_resume", { id: usage.node_id, at });
            setUsage(null);
          }}
        />
      )}
      {showTemplates && (
        <TemplatesDialog
          state={state}
          onSave={(payload) => request("templates", payload)}
          onOneOff={(payload) => request("one_off", payload)}
          onClose={() => setShowTemplates(false)}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}
