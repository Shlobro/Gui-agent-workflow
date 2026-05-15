# saves Developer Guide

## Purpose
`saves/` stores committed workflow JSON fixtures used for manual and regression testing of graph behavior in the GUI.

## Contents
- `simple_test.json`: baseline workflow fixture for quick load/run checks.
- `making-truncating-deleting-files.json`: fixture covering create/truncate/delete file-op node flows mixed with LLM nodes.
- `simple-review-loop.json`: automated review loop fixture that writes `review.txt`/`fixes-made.txt`, condition-checks `review.txt`, and repeats until the review file is empty. The two review LLM stages are intentionally named by role (`Review recent changes (initial)` and `Review recent changes (post-fix)`) to keep node names unique.
- `merge-rebase-with-review.json`: merge-or-rebase fixture. The target branch and mode are configured directly on two `VariableNode`s at the start of the graph (`branch` defaults to `master`, `mode` defaults to `merge`) and substituted into every downstream LLM prompt via `$branch` / `$mode`. Captures a baseline SHA in `pre-op-sha.txt`, runs the merge/rebase via a Claude resolver session, then dual-reviews the result (Claude + Codex sessions, each diffing against the baseline SHA for regression detection). An abort-decision LLM writes to `verdict.txt` to break the loop: non-empty verdict triggers `git merge --abort`/`git rebase --abort` and stops; empty verdict with both review files empty exits cleanly (workflow stops before push so the human can verify); otherwise an apply-feedback node consumes the reviews and the dual review re-runs.

## Usage Notes
- Keep fixtures deterministic and focused on one scenario per file.
- Use unique node names inside each fixture so manual run/debug screenshots are easy to reason about.
- Prefer relative filenames inside file-op nodes so fixtures remain portable across machines.
- Prefer stable model IDs in fixtures (avoid preview IDs unless the fixture is explicitly testing preview behavior).
- Treat fixtures as test assets: update them when node schema or execution behavior changes.
