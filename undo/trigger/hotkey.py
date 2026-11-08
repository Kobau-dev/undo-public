"""Global hotkey listener (pynput).

Default: double-tap Shift (⇧ ⇧), either side: one hand, no system or app conflict (double ⌥ can be bound to Siri).
UNDO_HOTKEY accepts either a double-tap spec "double:alt" (also "double:cmd", "double:ctrl", "double:shift",
"double:alt_r"...) or a classic pynput combo such as "<cmd>+<shift>+<alt>+z".
"""
from __future__ import annotations

import platform
import threading
import time
from typing import Callable

from undo.log import get_logger

log = get_logger("hotkey")

DOUBLE_TAP_WINDOW = 0.4  # seconds between the two taps

_SYMBOLS = {"cmd": "⌘", "shift": "⇧", "alt": "⌥", "ctrl": "⌃"}


def hotkey_label(combo: str) -> str:
    """Human label for the overlay / messages: 'double:alt' -> '⌥ ⌥', '<cmd>+<shift>+z' -> '⌘⇧Z'."""
    if combo.startswith("double:"):
        key = combo.split(":", 1)[1]
        sym = _SYMBOLS.get(key.split("_")[0], key)
        side = " droite" if key.endswith("_r") else " gauche" if key.endswith("_l") else ""
        return f"{sym} {sym}{side}"
    parts = [p.strip("<>") for p in combo.split("+")]
    return "".join(_SYMBOLS.get(p, p.upper()) for p in parts)


class DoubleTap:
    """Pure state machine: a modifier pressed and released twice in a row, alone, within `window` seconds."""

    def __init__(self, window: float = DOUBLE_TAP_WINDOW):
        self.window = window
        self._down = False
        self._clean = False  # no other key while the modifier was down
        self._last_tap = 0.0

    def press(self, is_target: bool, now: float) -> None:
        if is_target:
            if not self._down:
                self._down, self._clean = True, True
        else:
            # any other key cancels: Option is also used to type characters (⌥+key) and in shortcuts
            self._clean = False
            self._last_tap = 0.0

    def release(self, is_target: bool, now: float) -> bool:
        if not is_target or not self._down:
            return False
        self._down = False
        if not self._clean:
            self._last_tap = 0.0
            return False
        if self._last_tap and now - self._last_tap <= self.window:
            self._last_tap = 0.0
            return True
        self._last_tap = now
        return False


def prime_pynput() -> None:
    """Resolve pynput's lazy PyObjC symbol once on the calling thread. Several pynput listeners starting together
    (hotkey, Escape, input log) race inside PyObjC's lazy import and one dies with KeyError: 'AXIsProcessTrusted'."""
    if platform.system() != "Darwin":
        return
    try:
        import HIServices  # type: ignore

        HIServices.AXIsProcessTrusted()
    except Exception as exc:  # pragma: no cover
        log.debug("prime pynput failed: %s", exc)


class HotkeyListener:
    def __init__(self, combo: str, on_press: Callable[[], None]):
        self.combo = combo
        self.on_press = on_press
        self._listener = None

    def start(self) -> None:
        prime_pynput()
        from pynput import keyboard

        if self.combo.startswith("double:"):
            self._listener = self._double_tap_listener(keyboard, self.combo.split(":", 1)[1])
        else:
            self._listener = keyboard.GlobalHotKeys({self.combo: self._fire})
        self._listener.daemon = True
        self._listener.start()
        log.info("hotkey armed: %s (%s)", hotkey_label(self.combo), self.combo)

    def _double_tap_listener(self, keyboard, name: str):
        base = name.split("_")[0]
        if name.endswith(("_l", "_r")):
            targets = {getattr(keyboard.Key, name)}
        else:
            targets = {getattr(keyboard.Key, k) for k in (base, f"{base}_l", f"{base}_r") if hasattr(keyboard.Key, k)}
        tap = DoubleTap()

        def on_press(key):
            tap.press(key in targets, time.monotonic())

        def on_release(key):
            if tap.release(key in targets, time.monotonic()):
                self._fire()

        return keyboard.Listener(on_press=on_press, on_release=on_release)

    def _fire(self) -> None:
        threading.Thread(target=self.on_press, name="undo-hotkey", daemon=True).start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


class EscapeListener:
    """Fires `on_escape` when the user presses Esc — the executor kill switch."""

    def __init__(self, on_escape: Callable[[], None]):
        self.on_escape = on_escape
        self._listener = None

    def start(self) -> None:
        prime_pynput()
        from pynput import keyboard

        def handler(key):
            if key == keyboard.Key.esc:
                self.on_escape()

        self._listener = keyboard.Listener(on_press=handler)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
