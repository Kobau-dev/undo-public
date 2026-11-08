"""Input controllers: real (pyautogui) and dry-run (log only). Same surface for the agent loop."""
from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Protocol

from undo.log import get_logger

log = get_logger("control")

# When the agent itself presses Esc (to close a menu or a text box), the global Esc kill switch sees the same key.
# self_esc_recent() lets the kill switch tell that synthetic press apart from a real one from the user.
_last_self_esc = 0.0
SELF_ESC_WINDOW = 0.6


def self_esc_recent() -> bool:
    return time.time() - _last_self_esc < SELF_ESC_WINDOW

_MAC_KEYS = {"cmd": "command", "command": "command", "opt": "option", "option": "option", "alt": "option", "ctrl": "ctrl", "control": "ctrl", "shift": "shift", "enter": "enter", "return": "enter", "esc": "esc", "escape": "esc", "tab": "tab", "space": "space", "backspace": "backspace", "delete": "delete", "up": "up", "down": "down", "left": "left", "right": "right", "home": "home", "end": "end", "pageup": "pageup", "pagedown": "pagedown"}


def parse_combo(combo: str) -> list[str]:
    parts = [p.strip().lower() for p in combo.replace("-", "+").split("+") if p.strip()]
    keys = [_MAC_KEYS.get(p, p) for p in parts]
    if platform.system() != "Darwin":
        keys = ["ctrl" if k == "command" else ("alt" if k == "option" else k) for k in keys]
    return keys


class Controller(Protocol):
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None: ...
    def move(self, x: int, y: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def key(self, combo: str) -> None: ...
    def scroll(self, x: int, y: int, dx: int, dy: int) -> None: ...
    def open_app(self, name: str) -> None: ...
    def wait(self, seconds: float) -> None: ...


class DryRunController:
    """Prints what would happen. Used by --dry-run and tests."""

    def __init__(self):
        self.log: list[str] = []

    def _rec(self, s: str) -> None:
        self.log.append(s)
        log.info("[dry-run] %s", s)

    def move(self, x, y):
        self._rec(f"move({x}, {y})")

    def click(self, x, y, button="left", clicks=1):
        self._rec(f"{'double_' if clicks == 2 else ''}{button}_click({x}, {y})")

    def type_text(self, text):
        self._rec(f"type({text!r})")

    def key(self, combo):
        self._rec(f"key({'+'.join(parse_combo(combo))})")

    def scroll(self, x, y, dx, dy):
        self._rec(f"scroll({x}, {y}, dx={dx}, dy={dy})")

    def open_app(self, name):
        self._rec(f"open_app({name!r})")

    def wait(self, seconds):
        self._rec(f"wait({seconds})")


class PyAutoGUIController:
    def __init__(self, type_interval: float = 0.01):
        import pyautogui

        pyautogui.FAILSAFE = False  # we have our own ESC kill switch
        pyautogui.PAUSE = 0.05
        self.pg = pyautogui
        self.type_interval = type_interval

    def move(self, x, y):
        self.pg.moveTo(x, y, duration=0.15)

    def click(self, x, y, button="left", clicks=1):
        self.pg.moveTo(x, y, duration=0.15)
        self.pg.click(x, y, clicks=clicks, interval=0.08, button=button)

    def type_text(self, text):
        # pyautogui.write drops non-ASCII (accents), and on macOS also drops keystrokes on busy web pages -> paste
        if text.isascii() and platform.system() != "Darwin":
            self.pg.write(text, interval=self.type_interval)
            return
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                self._paste(line)
            if i < len(lines) - 1:
                self.key("enter")

    def _paste(self, text: str) -> None:
        """Enter non-ASCII text: clipboard paste on macOS; on Linux xdotool types unicode directly (pyperclip is
        unreliable there: e.g. the KDE klipper backend fails silently and pastes nothing)."""
        if platform.system() == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=False)
            time.sleep(0.05)
            # pyautogui.hotkey can release Cmd before V lands (a lone "v" gets typed); hold it explicitly
            from pynput.keyboard import Controller, Key

            kb = Controller()
            with kb.pressed(Key.cmd):
                time.sleep(0.03)
                kb.press("v")
                kb.release("v")
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "type", "--delay", "15", "--", text], check=False)
        elif shutil.which("xclip"):
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=False)
            self.pg.hotkey("ctrl", "v")
        else:
            self.pg.write(text.encode("ascii", "ignore").decode(), interval=self.type_interval)
        time.sleep(0.1)

    def key(self, combo):
        global _last_self_esc
        keys = parse_combo(combo)
        if "esc" in keys:
            _last_self_esc = time.time()
        if platform.system() == "Darwin" and keys and self._mac_hotkey(keys):
            return
        if len(keys) == 1:
            self.pg.press(keys[0])
        else:
            self.pg.hotkey(*keys)

    @staticmethod
    def _mac_hotkey(keys: list[str]) -> bool:
        """pyautogui on macOS drops keys on web pages and can release modifiers too early (Cmd+R typed as "r")."""
        from pynput.keyboard import Controller, Key

        names = {"command": Key.cmd, "option": Key.alt, "ctrl": Key.ctrl, "shift": Key.shift, "enter": Key.enter,
                 "esc": Key.esc, "tab": Key.tab, "space": Key.space, "backspace": Key.backspace, "delete": Key.delete,
                 "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right, "home": Key.home,
                 "end": Key.end, "pageup": Key.page_up, "pagedown": Key.page_down}
        resolved = [names.get(k, k) for k in keys]
        if any(isinstance(k, str) and len(k) != 1 for k in resolved):
            return False
        kb = Controller()
        for k in resolved[:-1]:
            kb.press(k)
            time.sleep(0.03)
        kb.press(resolved[-1])
        time.sleep(0.03)
        kb.release(resolved[-1])
        time.sleep(0.03)
        for k in reversed(resolved[:-1]):
            kb.release(k)
        return True

    @staticmethod
    def _lines(v: int) -> int:
        """The model sometimes sends pixels (dy=-3000) instead of wheel lines: rescale and cap to ~a screen."""
        if abs(v) > 25:
            v = round(v / 30)
        return max(-15, min(15, v))

    def scroll(self, x, y, dx, dy):
        dx, dy = self._lines(dx), self._lines(dy)
        self.pg.moveTo(x, y, duration=0.1)
        if dy:
            self.pg.scroll(dy)
        if dx:
            self.pg.hscroll(dx)

    def open_app(self, name):
        if platform.system() == "Darwin":
            subprocess.run(["open", "-a", name], check=False)
        else:
            subprocess.Popen([name.lower()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)

    def wait(self, seconds):
        time.sleep(min(float(seconds), 10.0))
