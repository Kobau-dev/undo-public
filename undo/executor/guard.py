"""What the user sees and can do while the agent acts: input lock (ESC stops) + Siri-like glow.
Both are macOS-only and off in --dry-run; the glow runs in a child process and dies with us."""
from __future__ import annotations

import platform
import subprocess
import sys
import threading
from typing import Callable

from undo.log import get_logger

log = get_logger("guard")


class ExecutionGuard:
    def __init__(self, on_esc: Callable[[], None], lock: bool = True, glow: bool = True, enabled: bool = True, on_blocked: Callable[[], None] | None = None):
        self.enabled = enabled and platform.system() == "Darwin"
        self.lock = None
        self._glow: subprocess.Popen | None = None
        if self.enabled and lock:
            from undo.executor.lock import InputLock

            self.lock = InputLock(on_esc=self._esc, on_blocked=on_blocked or (lambda: None))
        self.on_esc = on_esc
        self._want_glow = self.enabled and glow

    def start(self) -> None:
        if self._want_glow:
            try:
                self._glow = subprocess.Popen([sys.executable, "-m", "undo.ui.glow"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            except Exception as exc:
                log.debug("glow unavailable: %s", exc)
        if self.lock:
            self.lock.start()

    def _esc(self) -> None:
        self.on_esc()
        threading.Thread(target=self.stop, name="undo-guard-stop", daemon=True).start()

    def stop(self) -> None:
        if self.lock:
            self.lock.stop()
        glow, self._glow = self._glow, None
        if glow:
            self._send(glow, "quit")
            try:
                glow.wait(timeout=2)
            except Exception:
                glow.kill()

    @staticmethod
    def _send(glow: subprocess.Popen, line: str) -> None:
        if glow.stdin:
            try:
                glow.stdin.write(line.replace("\n", " ") + "\n")
                glow.stdin.flush()
            except Exception:
                pass
