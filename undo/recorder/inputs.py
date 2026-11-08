"""Local input log: what the user typed (grouped per window), keyboard shortcuts and clicks.

Lets Undo recover text that never appeared on screen (below the fold, a field scrolled away) and see the exact
action behind a mistake (Cmd+W, a click on "Delete"). Safeguards: nothing is logged while macOS secure input is on
(password fields), in excluded apps, or while the recorder is paused (e.g. while Undo itself is typing).
Stored only in the local SQLite index, purged with the frames.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import platform
import threading
import time
from typing import Callable

from undo.log import get_logger

log = get_logger("inputs")

FLUSH_IDLE = 3.0  # seconds without typing -> the text chunk is stored


def secure_input_enabled() -> bool:
    """macOS turns on "secure event input" while a password field has the focus."""
    if platform.system() != "Darwin":
        return False
    try:
        carbon = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Carbon"))
        carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool
        return bool(carbon.IsSecureEventInputEnabled())
    except Exception:
        return False


class TypedBuffer:
    """Pure text accumulator (testable): characters, backspace, enter; flushed as one 'typed' chunk."""

    def __init__(self):
        self.text = ""
        self.started = 0.0
        self.last = 0.0

    def char(self, c: str, now: float) -> None:
        if not self.text:
            self.started = now
        self.text += c
        self.last = now

    def backspace(self, now: float) -> None:
        self.text = self.text[:-1]
        self.last = now

    def take(self) -> tuple[float, str]:
        out = (self.started, self.text)
        self.text = ""
        return out


class InputLogger:
    def __init__(self, store: Callable[[float, str, str, str, str], None], foreground, is_excluded: Callable[[str, str], bool], is_paused: Callable[[], bool]):
        self.store = store
        self.foreground = foreground
        self.is_excluded = is_excluded
        self.is_paused = is_paused
        self.buf = TypedBuffer()
        self._window = ("", "")
        self._mods: set[str] = set()
        self._lock = threading.Lock()
        self._listeners: list = []
        self._stop = threading.Event()

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        from undo.trigger.hotkey import prime_pynput

        prime_pynput()
        from pynput import keyboard, mouse

        self._kb_mod = keyboard
        k = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        m = mouse.Listener(on_click=self._on_click)
        for listener in (k, m):
            listener.daemon = True
            listener.start()
        self._listeners = [k, m]
        threading.Thread(target=self._idle_flusher, name="undo-inputs", daemon=True).start()
        log.info("input log on (typed text, shortcuts, clicks; off in password fields)")

    def stop(self) -> None:
        self._stop.set()
        for listener in self._listeners:
            listener.stop()
        self.flush()

    # -- events ------------------------------------------------------------------
    def _blocked(self) -> bool:
        if self.is_paused() or secure_input_enabled():
            return True
        from undo import ax

        return ax.focused_is_password()

    def _mod_name(self, key) -> str | None:
        K = self._kb_mod.Key
        for name in ("cmd", "ctrl", "alt", "shift"):
            if key in {getattr(K, n, None) for n in (name, f"{name}_l", f"{name}_r")}:
                return name
        return None

    def _on_press(self, key) -> None:
        try:
            mod = self._mod_name(key)
            if mod:
                self._mods.add(mod)
                return
            if self._blocked():
                with self._lock:
                    self.buf.take()  # never keep text typed around a password field
                return
            now = time.time()
            K = self._kb_mod.Key
            char = getattr(key, "char", None)
            if self._mods & {"cmd", "ctrl"}:
                name = (char or str(key).replace("Key.", "")).lower()
                self.flush()
                self._store(now, "shortcut", "+".join(sorted(self._mods - {"shift"}) + (["shift"] if "shift" in self._mods else [])) + "+" + name)
                return
            with self._lock:
                if not self.buf.text:
                    self._window = self.foreground.foreground()
                if char:
                    self.buf.char(char, now)
                elif key == K.space:
                    self.buf.char(" ", now)
                elif key == K.backspace:
                    self.buf.backspace(now)
                elif key in (K.enter, K.tab):
                    self.buf.char("\n" if key == K.enter else "\t", now)
                else:
                    return
            if key in (K.enter, K.tab):
                self.flush()
        except Exception as exc:  # a logger must never crash the recorder
            log.debug("key event failed: %s", exc)

    def _on_release(self, key) -> None:
        mod = self._mod_name(key)
        if mod:
            self._mods.discard(mod)

    def _on_click(self, x, y, button, pressed) -> None:
        if not pressed or self._blocked():
            return
        self.flush()
        self._store(time.time(), "click", f"{int(x)},{int(y)} {getattr(button, 'name', button)}", window=self.foreground.foreground())

    # -- storage ---------------------------------------------------------------
    def _idle_flusher(self) -> None:
        while not self._stop.wait(1.0):
            if self.buf.text and time.time() - self.buf.last > FLUSH_IDLE:
                self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self.buf.text.strip():
                self.buf.take()
                return
            ts, text = self.buf.take()
            window = self._window
        self._store(ts, "typed", text, window=window)

    def _store(self, ts: float, kind: str, text: str, window: tuple[str, str] | None = None) -> None:
        app, title = window or self.foreground.foreground()
        if self.is_excluded(app, title):
            return
        try:
            self.store(ts, app, title, kind, text)
        except Exception as exc:
            log.debug("store input failed: %s", exc)


def format_inputs(rows: list[dict], now: float, max_chars: int = 3000) -> str:
    """Timeline block for the Analyzer prompt (typed text and shortcuts; clicks are summarised)."""
    from undo.analyzer.search import relative_time

    lines = []
    for r in rows:
        if r["kind"] == "click":
            continue
        what = f"typed «{r['text'].strip()}»" if r["kind"] == "typed" else f"shortcut {r['text']}"
        lines.append(f"- {relative_time(r['ts'], now)} | {r['app'] or '?'} | {r['window_title'] or '?'} | {what}")
    if not lines:
        return ""
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = "[…]\n" + text[-max_chars:]
    return "KEYBOARD LOG (what the user actually typed, exact text, oldest first; may include text never visible on screen):\n" + text
