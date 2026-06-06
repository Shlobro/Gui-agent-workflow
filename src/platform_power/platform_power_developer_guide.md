# Platform Power Developer Guide

## Purpose
`src/platform_power` keeps the host machine from sleeping or shutting down while
a workflow is actively running, and releases that guarantee the moment the
workflow is idle, finished, stopped, or blocked waiting for the user. Only the
*system* is kept awake; the display is left free to turn off normally.

## Public Surface
Import from the package, not the module:

```python
from src.platform_power import prevent_sleep, allow_sleep, sleep_prevented
```

- `prevent_sleep()`: keep the system and display awake. Idempotent.
- `allow_sleep()`: restore the OS's normal idle sleep/timeout behavior. Idempotent.
- `sleep_prevented() -> bool`: True while sleep is currently being prevented.

All three are safe to call on any platform; on non-Windows hosts they are
no-ops (and `sleep_prevented()` stays False).

## Implementation (`sleep_inhibitor.py`)
On Windows the inhibitor calls the Win32 `SetThreadExecutionState` API via
`ctypes`:
- `prevent_sleep()` passes `ES_CONTINUOUS | ES_SYSTEM_REQUIRED` (no
  `ES_DISPLAY_REQUIRED`, so the monitor may still sleep).
- `allow_sleep()` passes `ES_CONTINUOUS` alone, clearing the request.

State is a single process-global flag (`_sleep_prevented`), not a reference
count: callers turn the guarantee on while work is active and off otherwise. The
OS resets the execution state automatically when the process exits, so no
shutdown cleanup is required.

## Who Calls It
- `src/gui/main_window.py` `_on_run_state_changed(running)`: calls
  `prevent_sleep()` when the canvas `run_state_changed` signal reports a run
  started, and `allow_sleep()` when it reports the run stopped/finished.
- `src/gui/canvas/execution.py` `_fire_attention(...)`: while the modal
  Attention dialog blocks waiting for the user, it temporarily `allow_sleep()`s
  and re-arms `prevent_sleep()` afterward only if a run is still active.
