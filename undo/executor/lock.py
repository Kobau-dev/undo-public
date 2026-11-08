"""macOS input lock while the agent drives the computer.

A CGEventTap swallows every keyboard/mouse event that does not come from this process (pyautogui posts its events
with our pid), so the user cannot type into the middle of a restoration by accident. Escape always goes through and
stops the agent. The tap dies with the process (no way to leave the machine locked) and is a no-op elsewhere.
Needs the Accessibility permission (already required to control the mouse)."""
from __future__ import annotations

import os
import platform
import threading
import time
from typing import Callable

from undo.log import get_logger

log = get_logger("lock")

ESC_KEYCODE = 53


class InputLock:
    def __init__(self, on_esc: Callable[[], None], on_blocked: Callable[[], None] | None = None):
        self.on_esc = on_esc
        self.on_blocked = on_blocked
        self._loop = None
        self._tap = None
        self._thread: threading.Thread | None = None
        self._last_warn = 0.0
        self.active = False

    def start(self) -> None:
        if platform.system() != "Darwin":
            return
        self._thread = threading.Thread(target=self._run, name="undo-lock", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        loop, self._loop = self._loop, None
        if not loop:
            return
        try:
            import Quartz  # type: ignore

            if self._tap:
                Quartz.CGEventTapEnable(self._tap, False)
            Quartz.CFRunLoopStop(loop)
        except Exception as exc:  # pragma: no cover
            log.debug("lock stop failed: %s", exc)
        self.active = False

    def _run(self) -> None:
        try:
            import Quartz  # type: ignore
        except Exception as exc:  # pragma: no cover
            log.warning("input lock unavailable: %s", exc)
            return
        me = os.getpid()
        types = [
            Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp, Quartz.kCGEventFlagsChanged,
            Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp,
            Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp, Quartz.kCGEventMouseMoved,
            Quartz.kCGEventLeftMouseDragged, Quartz.kCGEventRightMouseDragged, Quartz.kCGEventScrollWheel,
        ]
        moves = (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDragged, Quartz.kCGEventRightMouseDragged)
        self._pos = None
        mask = 0
        for t in types:
            mask |= Quartz.CGEventMaskBit(t)

        def callback(proxy, type_, event, refcon):
            if type_ in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
                Quartz.CGEventTapEnable(self._tap, True)
                return event
            if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID) == me:
                if type_ in moves:
                    self._pos = Quartz.CGEventGetLocation(event)
                return event  # our own synthetic action
            if type_ in moves:
                # swallowing a move does not stop the hardware cursor: put it back where the agent left it
                if self._pos is None:
                    self._pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                Quartz.CGWarpMouseCursorPosition(self._pos)
            if type_ == Quartz.kCGEventKeyDown and Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode) == ESC_KEYCODE:
                log.info("ESC pressed by the user: stopping")
                self.on_esc()
                self.stop()  # give the keyboard and mouse back now, not when the current model call returns
                return None
            if type_ != Quartz.kCGEventMouseMoved and self.on_blocked and time.time() - self._last_warn > 0.7:
                self._last_warn = time.time()
                self.on_blocked()
            return None  # swallowed

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap, Quartz.kCGEventTapOptionDefault, mask, callback, None
        )
        if not self._tap:
            log.warning("input lock: CGEventTapCreate failed (Accessibility permission missing?)")
            return
        src = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, src, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        self.active = True
        log.info("input locked (ESC stops)")
        Quartz.CFRunLoopRun()
        log.info("input unlocked")
