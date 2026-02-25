"""QThread-based LLM worker with streaming output."""

import subprocess
import sys
import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal

from src.llm.base_provider import BaseLLMProvider


class LLMWorker(QThread):
    output_line = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, provider: BaseLLMProvider, prompt: str,
                 model: Optional[str] = None,
                 working_directory: Optional[str] = None,
                 timeout: int = 3600):
        super().__init__()
        self.provider = provider
        self.prompt = prompt
        self.model = model
        self.working_directory = working_directory
        self.timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._output_lines = []
        self._lock = threading.Lock()

    def run(self):
        try:
            command = self.provider.build_command(
                self.prompt,
                model=self.model,
                working_directory=self.working_directory,
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

            # Send prompt via stdin
            self._process.stdin.write(self.provider.get_stdin_prompt(self.prompt))
            self._process.stdin.close()

            # Read output line by line
            for line in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    break
                stripped = line.rstrip("\n\r")
                with self._lock:
                    self._output_lines.append(stripped)
                self.output_line.emit(stripped)

            self._process.wait(timeout=self.timeout)

            if not self._cancelled:
                full_output = "\n".join(self._output_lines)
                self.finished.emit(full_output)

        except FileNotFoundError:
            cmd_name = self.provider.build_command("", model=self.model)[0]
            self.error.emit(
                f"Command not found: '{cmd_name}'. "
                f"Is {self.provider.display_name} CLI installed and in PATH?"
            )
        except subprocess.TimeoutExpired:
            if self._process:
                self._process.kill()
            self.error.emit(f"Timed out after {self.timeout}s")
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            except Exception:
                pass
