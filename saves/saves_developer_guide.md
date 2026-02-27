# saves Developer Guide

## Purpose
`saves/` stores committed workflow JSON fixtures used for manual and regression testing of graph behavior in the GUI.

## Contents
- `simple_test.json`: baseline workflow fixture for quick load/run checks.
- `making-truncating-deleting-files.json`: fixture covering create/truncate/delete file-op node flows mixed with LLM nodes.

## Usage Notes
- Keep fixtures deterministic and focused on one scenario per file.
- Use unique node names inside each fixture so manual run/debug screenshots are easy to reason about.
- Prefer relative filenames inside file-op nodes so fixtures remain portable across machines.
- Prefer stable model IDs in fixtures (avoid preview IDs unless the fixture is explicitly testing preview behavior).
- Treat fixtures as test assets: update them when node schema or execution behavior changes.
