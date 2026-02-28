"""QThread-based worker for running git subprocess commands."""

import os
import subprocess
import threading
from typing import Optional, Sequence

from PySide6.QtCore import QThread, Signal


class GitWorker(QThread):
    """Run a git command in a background thread with cancellation support."""

    output_line = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, command: Sequence[str],
                 working_directory: Optional[str] = None,
                 timeout: int = 3600):
        super().__init__()
        self.command = list(command)
        self.working_directory = working_directory
        self.timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._timed_out = False
        self._output_lines: list[str] = []
        self._lock = threading.Lock()

    def _terminate_process(self):
        """Kill the subprocess if it is running. Safe to call from any thread."""
        proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass

    def _start_timeout_watchdog(self, done_event: threading.Event):
        """Terminate the subprocess when timeout is reached, even if stdout is quiet."""
        if self.timeout <= 0:
            return

        def _watchdog():
            if done_event.wait(self.timeout):
                return
            proc = self._process
            if self._cancelled or proc is None or proc.poll() is not None:
                return
            self._timed_out = True
            self._terminate_process()

        threading.Thread(target=_watchdog, daemon=True).start()

    def run(self):
        done_event = threading.Event()
        try:
            if self._cancelled:
                self.error.emit("Cancelled")
                return
            if self.working_directory and not os.path.isdir(self.working_directory):
                self.error.emit(f"Working directory not found: {self.working_directory}")
                return

            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.working_directory or None,
                bufsize=1,
                universal_newlines=True,
            )

            if self._cancelled:
                self._terminate_process()
                self.error.emit("Cancelled")
                return

            self._start_timeout_watchdog(done_event)

            if self._process.stdout is not None:
                for line in iter(self._process.stdout.readline, ""):
                    if self._cancelled or self._timed_out:
                        break
                    stripped = line.rstrip("\n\r")
                    with self._lock:
                        self._output_lines.append(stripped)
                    self.output_line.emit(stripped)

            if self._cancelled:
                self._terminate_process()
                self.error.emit("Cancelled")
                return

            if self._timed_out:
                self.error.emit(f"Timed out after {self.timeout}s")
                return

            while self._process.poll() is None:
                if self._cancelled:
                    self._terminate_process()
                    self.error.emit("Cancelled")
                    return
                if self._timed_out:
                    self.error.emit(f"Timed out after {self.timeout}s")
                    return
                self.msleep(50)

            if self._cancelled:
                self.error.emit("Cancelled")
                return
            if self._timed_out:
                self.error.emit(f"Timed out after {self.timeout}s")
                return

            full_output = "\n".join(self._output_lines).strip()
            if self._process.returncode != 0:
                # Detailed command output is already streamed line-by-line via output_line.
                # Emit only a concise terminal failure summary to avoid duplicated logs.
                self.error.emit(f"git command failed (exit {self._process.returncode})")
                return

            self.finished.emit(full_output)

        except FileNotFoundError:
            # Popen raises FileNotFoundError for both missing command and bad cwd.
            if self.working_directory and not os.path.isdir(self.working_directory):
                self.error.emit(f"Working directory not found: {self.working_directory}")
            else:
                cmd_name = self.command[0] if self.command else "git"
                self.error.emit(
                    f"Command not found: '{cmd_name}'. Is git installed and in PATH?"
                )
        except subprocess.TimeoutExpired:
            if self._process:
                self._process.kill()
            self.error.emit(f"Timed out after {self.timeout}s")
        except Exception as exc:
            self.error.emit("Cancelled" if self._cancelled else str(exc))
        finally:
            done_event.set()

    def cancel(self):
        """Signal the worker to stop without blocking the caller."""
        self._cancelled = True
        proc = self._process
        if proc and proc.poll() is None:
            def _kill():
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    pass

            t = threading.Thread(target=_kill, daemon=True)
            t.start()
