"""Always-on-top floating overlay (tkinter) — what the jury sees.

tkinter must run on the main thread on macOS: `OverlayUI.start(worker)` runs the Tk mainloop and starts `worker` in a
background thread. All StatusSink methods are thread-safe (queued onto the Tk loop); `confirm`/`ask` block the caller.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import deque
from typing import Callable

try:
    import tkinter as tk
except ImportError:  # Homebrew Python ships without it: macOS uses the native HUD, build_ui falls back to the console elsewhere
    tk = None

from undo.log import get_logger
from undo.ui.console import STATE_LABELS
from undo.i18n import t

log = get_logger("overlay")

COLORS = {
    "idle": "#8b949e",
    "listening": "#f2cc60",
    "transcribing": "#f2cc60",
    "heard": "#58a6ff",
    "analyzing": "#58a6ff",
    "understood": "#58a6ff",
    "executing": "#d2a8ff",
    "done": "#3fb950",
    "failed": "#f85149",
    "stopped": "#f85149",
}


class OverlayUI:
    WIDTH = 440

    def __init__(self, title: str = "Undo", max_steps: int = 6, on_quit: Callable[[], None] | None = None, hotkey: str = "double:shift"):
        from undo.trigger.hotkey import hotkey_label

        self.title = title
        self.hotkey = hotkey_label(hotkey)
        self.max_steps = max_steps
        self.on_quit = on_quit
        self._q: queue.Queue[Callable[[], None]] = queue.Queue()
        self._steps: deque[str] = deque(maxlen=max_steps)
        self._root: tk.Tk | None = None
        self.state = "idle"

    # -- StatusSink (thread-safe) ---------------------------------------------
    def set_state(self, state: str, text: str = "") -> None:
        self.state = state
        if state in {"listening", "analyzing", "idle"}:
            self._steps.clear()
        self._q.put(lambda: self._render(state, text))

    def add_step(self, text: str) -> None:
        self._steps.append(text)
        self._q.put(lambda: self._render_steps())

    def confirm(self, question: str) -> bool:
        return bool(self._modal(question, with_entry=False))

    def ask(self, question: str) -> str:
        return str(self._modal(question, with_entry=True) or "")

    def prompt_input(self, question: str, on_submit: Callable[[str], None]) -> Callable[[], None]:
        """Non-blocking text box shown while Undo listens: type the request + Enter instead of speaking.
        Returns a function that closes the box."""
        import platform

        if platform.system() == "Darwin":
            return _native_prompt(question, on_submit)
        holder: dict = {}

        def build():
            top = tk.Toplevel(self._root)
            holder["top"] = top
            top.title("Undo")
            top.attributes("-topmost", True)
            top.configure(bg="#161b22", padx=16, pady=14)
            sw = top.winfo_screenwidth()
            top.geometry(f"+{(sw - 520) // 2}+140")
            tk.Label(top, text=question, fg="#e6edf3", bg="#161b22", font=("Helvetica", 13), wraplength=480, justify="left").pack(anchor="w")
            entry = tk.Entry(top, width=52, font=("Helvetica", 14))
            entry.pack(pady=(10, 0))

            def submit(_e=None):
                text = entry.get().strip()
                if text:
                    close_now()
                    on_submit(text)

            entry.bind("<Return>", submit)
            entry.bind("<Escape>", lambda e: close_now())
            top.protocol("WM_DELETE_WINDOW", close_now)
            _activate()
            top.lift()
            top.focus_force()
            entry.focus_force()

        def close_now():
            top = holder.pop("top", None)
            if top is not None:
                try:
                    top.destroy()
                except tk.TclError:
                    pass

        self._q.put(build)
        return lambda: self._q.put(close_now)

    # -- lifecycle ---------------------------------------------------------------
    def start(self, worker: Callable[[], None]) -> None:
        root = tk.Tk()
        self._root = root
        root.title(self.title)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        root.configure(bg="#0d1117")
        sw = root.winfo_screenwidth()
        root.geometry(f"{self.WIDTH}x180+{sw - self.WIDTH - 24}+48")

        self._dot = tk.Label(root, text="●", fg=COLORS["idle"], bg="#0d1117", font=("Helvetica", 18))
        self._dot.place(x=14, y=10)
        self._title = tk.Label(root, text=f"Undo — {t('Ready')}", fg="#e6edf3", bg="#0d1117", font=("Helvetica", 15, "bold"), anchor="w")
        self._title.place(x=40, y=12, width=self.WIDTH - 90)
        self._hint = tk.Label(root, text=self.hotkey, fg="#8b949e", bg="#0d1117", font=("Helvetica", 11), anchor="e")
        self._hint.place(x=self.WIDTH - 130, y=16, width=114)
        self._text = tk.Label(root, text=t("Press {hotkey} and say what you want back.", hotkey=self.hotkey), fg="#c9d1d9", bg="#0d1117", font=("Helvetica", 12), anchor="nw", justify="left", wraplength=self.WIDTH - 40)
        self._text.place(x=18, y=46, width=self.WIDTH - 36, height=60)
        self._stepsbox = tk.Label(root, text="", fg="#8b949e", bg="#0d1117", font=("Menlo", 10), anchor="nw", justify="left", wraplength=self.WIDTH - 40)
        self._stepsbox.place(x=18, y=108, width=self.WIDTH - 36, height=66)

        # drag to move
        def start_drag(e):
            root._drag = (e.x, e.y)

        def do_drag(e):
            dx, dy = root._drag
            root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

        for w in (root, self._title, self._text):
            w.bind("<ButtonPress-1>", start_drag)
            w.bind("<B1-Motion>", do_drag)
        root.bind("<Double-Button-1>", lambda e: self.quit())

        threading.Thread(target=worker, name="undo-main", daemon=True).start()
        root.after(50, self._pump)
        root.mainloop()

    def quit(self) -> None:
        if self.on_quit:
            self.on_quit()
        if self._root:
            self._root.after(0, self._root.destroy)

    # -- internals ---------------------------------------------------------------
    def _pump(self) -> None:
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        if self._root:
            self._root.after(50, self._pump)

    def _render(self, state: str, text: str) -> None:
        self._dot.configure(fg=COLORS.get(state, "#8b949e"))
        self._title.configure(text=f"Undo — {t(STATE_LABELS.get(state, state))}")
        self._text.configure(text=text)
        self._render_steps()
        if state in {"done", "failed"} and self._root:
            self._root.after(12000, lambda: self.state in {"done", "failed"} and self._render("idle", t("Press {hotkey} and say what you want back.", hotkey=self.hotkey)))

    def _render_steps(self) -> None:
        self._stepsbox.configure(text="\n".join(f"{'▸' if i == len(self._steps) - 1 else '✓'} {s}" for i, s in enumerate(self._steps)))
        if self._root:
            h = 120 + 16 * max(1, len(self._steps))
            geo = self._root.geometry().split("+", 1)
            self._root.geometry(f"{self.WIDTH}x{h}+{geo[1]}" if len(geo) == 2 else f"{self.WIDTH}x{h}")

    def _modal(self, question: str, with_entry: bool):
        done = threading.Event()
        result: list = [None]

        def build():
            top = tk.Toplevel(self._root)
            top.title("Undo")
            top.attributes("-topmost", True)
            top.configure(bg="#161b22", padx=16, pady=14)
            tk.Label(top, text=question, fg="#e6edf3", bg="#161b22", font=("Helvetica", 13), wraplength=380, justify="left").pack(anchor="w")
            entry = None
            if with_entry:
                entry = tk.Entry(top, width=48, font=("Helvetica", 12))
                entry.pack(pady=(10, 0))
                entry.focus_set()
            row = tk.Frame(top, bg="#161b22")
            row.pack(pady=(12, 0), anchor="e")

            def finish(val):
                result[0] = val
                top.destroy()
                done.set()

            if with_entry:
                tk.Button(row, text="OK", command=lambda: finish(entry.get())).pack(side="right")
                entry.bind("<Return>", lambda e: finish(entry.get()))
            else:
                tk.Button(row, text="Continuer", command=lambda: finish(True)).pack(side="right", padx=(8, 0))
                tk.Button(row, text="Annuler", command=lambda: finish(False)).pack(side="right")
            top.protocol("WM_DELETE_WINDOW", lambda: finish("" if with_entry else False))
            _activate()
            top.lift()
            top.focus_force()
            if entry is not None:
                entry.focus_force()

        self._q.put(build)
        done.wait()
        return result[0]


def _activate() -> None:
    """Bring our (background) Python process to the front so the text box receives the keyboard."""
    try:
        import platform

        if platform.system() == "Darwin":
            import AppKit  # type: ignore

            AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception as exc:  # pragma: no cover
        log.debug("activate failed: %s", exc)


def build_ui(no_ui: bool = False, auto_confirm: bool = False, hotkey: str = "double:shift"):
    if no_ui:
        from undo.ui.console import ConsoleUI

        return ConsoleUI(auto_confirm=auto_confirm)
    import platform

    if platform.system() == "Darwin":
        return MacHudUI(hotkey=hotkey)
    try:
        import tkinter  # noqa: F401

        return OverlayUI(hotkey=hotkey)
    except Exception as exc:  # pragma: no cover
        log.warning("tkinter unavailable (%s), falling back to console UI", exc)
        from undo.ui.console import ConsoleUI

        return ConsoleUI(auto_confirm=auto_confirm)


def _native_prompt(question: str, on_submit: Callable[[str], None]) -> Callable[[], None]:
    """macOS: AppKit panel in a child process (see undo.ui.prompt_mac); the typed line comes back on stdout."""
    import subprocess
    import sys
    import threading

    proc = subprocess.Popen([sys.executable, "-m", "undo.ui.prompt_mac", question], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")

    def reader() -> None:
        line = (proc.stdout.readline() if proc.stdout else "").strip()
        if line:
            on_submit(line)

    threading.Thread(target=reader, daemon=True, name="undo-prompt").start()
    return lambda: proc.poll() is None and proc.terminate()


class MacHudUI:
    """macOS StatusSink: drives the native panel in undo.ui.hud_mac (Tk windows of a background process stay invisible)."""

    def __init__(self, hotkey: str = "double:shift"):
        import queue as _queue
        import threading

        self.hotkey = hotkey
        self.state = "idle"
        self._proc = None
        self._lock = threading.Lock()
        self._typed_cb: Callable[[str], None] | None = None
        self._answers: _queue.Queue[str] = _queue.Queue()
        self._last_level = 0.0
        self.on_escape: Callable[[], None] | None = None
        self.on_input_edited: Callable[[], None] | None = None  # the user started typing in the text box

    def _ensure(self):
        import subprocess
        import sys
        import threading

        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = subprocess.Popen([sys.executable, "-m", "undo.ui.hud_mac"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._reader, args=(self._proc,), daemon=True, name="undo-hud").start()
        return self._proc

    def _send(self, **msg) -> None:
        import json

        with self._lock:
            try:
                proc = self._ensure()
                proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                log.debug("hud send failed: %s", exc)

    def _reader(self, proc) -> None:
        import json

        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "typed" in msg:
                cb = self._typed_cb
                if cb:
                    cb(msg["typed"])
                else:
                    self._answers.put(msg["typed"])
            elif msg.get("editing"):
                if self.on_input_edited:
                    self.on_input_edited()
            elif msg.get("esc"):
                if self._typed_cb is None:
                    self._answers.put("")
                if self.on_escape:
                    self.on_escape()

    # -- StatusSink -------------------------------------------------------------
    def set_state(self, state: str, text: str = "") -> None:
        self.state = state
        self._send(cmd="state", state=state, text=text)

    def add_step(self, text: str) -> None:
        self._send(cmd="step", text=text)

    def warn(self) -> None:
        self._send(cmd="warn")

    def set_transcript(self, text: str) -> None:
        self._send(cmd="transcript", text=text)

    def set_level(self, value: float) -> None:
        now = time.time()
        if now - self._last_level >= 0.05:
            self._last_level = now
            self._send(cmd="level", value=round(value, 4))

    def confirm(self, question: str) -> bool:
        log.info("auto-confirmed (no modal on macOS HUD): %s", question)
        return True

    def ask(self, question: str, timeout: float = 60.0) -> str:
        import queue as _queue

        while not self._answers.empty():
            self._answers.get_nowait()
        self._typed_cb = None
        self._send(cmd="ask", text=question)
        try:
            return self._answers.get(timeout=timeout)
        except _queue.Empty:
            return ""

    def cancel_input(self) -> None:
        """Unblock a pending ask() with an empty answer (Esc pressed outside the bubble)."""
        self._answers.put("")

    def prompt_input(self, question: str, on_submit: Callable[[str], None]) -> Callable[[], None]:
        self._typed_cb = on_submit

        def close() -> None:
            self._typed_cb = None
            self.on_input_edited = None

        return close

    def fill_input(self, text: str | None) -> bool:
        """Put the transcript in the open text box (None: keep what the user is typing). Enter sends it, through prompt_input."""
        if self._typed_cb is None:
            return False
        self.state = "asking"
        self._send(cmd="input", text=text)
        return True

    # -- lifecycle --------------------------------------------------------------
    def start(self, worker: Callable[[], None]) -> None:
        import threading

        self._ensure()
        _prime_text_input_on_main_thread()
        t = threading.Thread(target=worker, daemon=True, name="undo-worker")
        t.start()
        try:
            from Foundation import NSDate, NSRunLoop

            # keep the main run loop serviced: macOS keyboard APIs used by pynput's threads dispatch to it
            while t.is_alive():
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.25))
        finally:
            self.quit()

    def quit(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._send(cmd="quit")
            try:
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.terminate()


def _prime_text_input_on_main_thread() -> None:
    """pynput listeners query the keyboard layout (TIS/TSM) from their own threads; macOS aborts the process unless
    that API was first initialised on the main thread (Tk used to do it implicitly)."""
    try:
        from pynput._util.darwin import keycode_context

        with keycode_context():
            pass
    except Exception as exc:
        log.debug("text input priming failed: %s", exc)
