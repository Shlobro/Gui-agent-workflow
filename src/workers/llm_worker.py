"""QThread-based LLM worker with streaming output."""

import subprocess
import sys
import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal

from src.llm.base_provider import BaseLLMProvider


class LLMWorker(QThread):
    output_line = Signal(str)
    finished = Signal(str, str)
    error = Signal(str, str)

    def __init__(self, provider: BaseLLMProvider, prompt: str,
                 model: Optional[str] = None,
                 session_id: Optional[str] = None,
                 working_directory: Optional[str] = None,
                 timeout: int = 3600):
        super().__init__()
        self.provider = provider
        self.prompt = prompt
        self.model = model
        self.session_id = session_id
        self.working_directory = working_directory
        self.timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._output_lines = []
        self._lock = threading.Lock()

    def _emit_error(self, message: str, session_id: str = "") -> None:
        self.error.emit(message, session_id)

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

    def run(self):
        try:
            # Check before spawning — cancel() may have fired before Popen
            if self._cancelled:
                self._emit_error("Cancelled")
                return

            command = self.provider.build_command(
                self.prompt,
                model=self.model,
                working_directory=self.working_directory,
                session_id=self.session_id,
            )
            use_shell = sys.platform == "win32" and command[0].lower() != "cmd"

            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.working_directory or None,
                bufsize=1,
                universal_newlines=True,
                shell=use_shell,
            )

            # Check again immediately after Popen in case cancel() raced
            if self._cancelled:
                self._terminate_process()
                self._emit_error("Cancelled")
                return

            # Send prompt via stdin when the provider expects it.
            if self.provider.uses_stdin and self._process.stdin is not None:
                self._process.stdin.write(self.provider.get_stdin_prompt(self.prompt))
            if self._process.stdin is not None:
                self._process.stdin.close()

            # Read output line by line
            structured_output = self.provider.uses_structured_output(self.model)
            for line in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    break
                stripped = line.rstrip("\n\r")
                with self._lock:
                    self._output_lines.append(stripped)
                if not structured_output:
                    self.output_line.emit(stripped)

            if self._cancelled:
                self._terminate_process()
                self._emit_error("Cancelled")
                return

            self._process.wait(timeout=self.timeout)
            if self._cancelled:
                self._emit_error("Cancelled")
                return
            full_output = "\n".join(self._output_lines)
            session_id = ""
            if structured_output:
                parsed_output, session_id = self.provider.parse_structured_output(self._output_lines)
                if parsed_output.strip():
                    full_output = parsed_output
            if self._process.returncode != 0:
                self._emit_error(full_output, session_id)
                return
            self.finished.emit(full_output, session_id)

        except FileNotFoundError:
            cmd_name = self.provider.build_command("", model=self.model)[0]
            self._emit_error(
                f"Command not found: '{cmd_name}'. "
                f"Is {self.provider.display_name} CLI installed and in PATH?",
            )
        except subprocess.TimeoutExpired:
            if self._process:
                self._process.kill()
            self._emit_error(f"Timed out after {self.timeout}s")
        except Exception as e:
            self._emit_error("Cancelled" if self._cancelled else str(e))

    def cancel(self):
        """Signal the worker to stop. Non-blocking: sets flag and spawns a
        daemon thread that runs terminate→wait(4s)→kill so the subprocess is
        guaranteed to die even if readline() is blocking the worker thread."""
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
