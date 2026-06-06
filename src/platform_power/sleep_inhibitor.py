"""Prevent the OS from sleeping/shutting down while a workflow runs.

The public surface is two idempotent calls -- ``prevent_sleep()`` and
``allow_sleep()`` -- plus a ``sleep_prevented()`` query. They are safe to call
repeatedly and on any platform: on non-Windows hosts they are no-ops.

On Windows the implementation uses the Win32 ``SetThreadExecutionState`` API.
Passing ``ES_CONTINUOUS`` together with ``ES_SYSTEM_REQUIRED`` tells the OS to keep the
system awake until the state is cleared. The display is intentionally *not*
pinned (no ``ES_DISPLAY_REQUIRED``), so the monitor may still turn off normally.
Clearing means calling the API again with
``ES_CONTINUOUS`` alone, which restores normal idle sleep/timeout behavior.

This is intentionally a process-global, single-flag inhibitor rather than a
reference count: callers turn the guarantee on while work is active and off when
the workflow is idle or waiting for the user.
"""

import sys

# Win32 SetThreadExecutionState flags.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001

_IS_WINDOWS = sys.platform.startswith("win")

_sleep_prevented = False


def _set_execution_state(flags: int) -> bool:
    """Call SetThreadExecutionState; return True on success, False otherwise."""
    if not _IS_WINDOWS:
        return False
    try:
        import ctypes

        result = ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
        return result != 0
    except Exception:
        return False


def prevent_sleep() -> None:
    """Keep the system awake until ``allow_sleep`` is called.

    The display is not pinned, so the monitor may still turn off. Idempotent:
    calling it while already preventing sleep simply refreshes the request. A
    no-op on non-Windows platforms.
    """
    global _sleep_prevented
    if _set_execution_state(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED):
        _sleep_prevented = True


def allow_sleep() -> None:
    """Restore normal idle sleep/shutdown behavior.

    Idempotent and a no-op on non-Windows platforms.
    """
    global _sleep_prevented
    if not _sleep_prevented:
        return
    _set_execution_state(_ES_CONTINUOUS)
    _sleep_prevented = False


def sleep_prevented() -> bool:
    """Return True while sleep is currently being prevented."""
    return _sleep_prevented
