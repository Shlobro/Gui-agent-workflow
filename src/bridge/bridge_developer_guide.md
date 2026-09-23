# Desktop Bridge Developer Guide

## Purpose
`src/bridge/` exposes the existing workflow engine to the Electron editor through a newline-delimited JSON protocol on standard input and output. The bridge owns a hidden Qt application because the current engine uses Qt scene items and worker signals.

## Files
- `server.py`: Creates the canvas, handles editor commands, and publishes graph and run snapshots. All canvas operations run on the Qt event loop. A reader thread only queues messages. Attention dialogs use a nested event loop with a separate request poller so a response can unblock the waiting branch.

## Protocol
Requests contain `id`, `action`, and `payload`. Replies contain the same `id`, `ok`, and either `result` or `error`. Unsolicited snapshots have `type: "state"`. Protocol lines begin with `@@GUI@@` so incidental process output cannot be mistaken for messages. Standard input, output, and error are forced to UTF-8 at startup, matching the Electron host regardless of the Windows console code page.

## Data Rules
- Load and save use the canvas's JSON parser and serializer. The editor does not translate workflow files.
- React owns temporary drag positions. The bridge applies positions when a drag ends.
- Run actions validate reachable nodes before entering the existing execution engine.
- `stop` cancels every worker and also releases any pending attention waits as "stop", so no branch stays blocked in a nested event loop. The editor closes an open attention dialog once a snapshot reports `running: false`.
- Loaded workflow sessions prompt for resume or fresh start before the next run. Prompt templates remain in the Python store, and a one-time injection stays active until the run finishes.
- The bridge is local to the desktop process and has no network listener.
