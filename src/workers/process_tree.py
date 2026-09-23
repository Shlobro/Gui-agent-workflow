"""Subprocess termination that also reaches grandchildren on Windows."""

from __future__ import annotations

import subprocess
import sys
import threading
from typing import Optional


def terminate_tree(proc: Optional[subprocess.Popen], grace: float = 4) -> None:
    """Stop ``proc`` and its descendants. Blocks until done; safe from any thread.

    Workers launch CLIs through ``cmd``/``powershell`` shims on Windows, where
    ``Popen.terminate`` only ends the shim and leaves the real tool running
    with the output pipe still open.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=grace,
            )
        else:
            proc.terminate()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def terminate_tree_async(proc: Optional[subprocess.Popen]) -> None:
    """Run :func:`terminate_tree` on a daemon thread so callers never block."""
    if proc is None or proc.poll() is not None:
        return
    threading.Thread(target=terminate_tree, args=(proc,), daemon=True).start()
