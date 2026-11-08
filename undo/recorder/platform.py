"""Foreground application + window title, per platform."""
from __future__ import annotations

import platform
import shutil
import subprocess

from undo.log import get_logger

log = get_logger("platform")


class StaticForeground:
    def __init__(self, app: str = "", title: str = ""):
        self._v = (app, title)

    def foreground(self) -> tuple[str, str]:
        return self._v


class MacForeground:
    """NSWorkspace for the app, CGWindowList for the title; falls back to osascript."""

    def __init__(self):
        try:
            from AppKit import NSWorkspace  # type: ignore
            import Quartz  # type: ignore

            self._ws = NSWorkspace.sharedWorkspace()
            self._quartz = Quartz
        except Exception as exc:  # pragma: no cover
            log.warning("pyobjc not available (%s); using osascript", exc)
            self._ws = None
            self._quartz = None
        self.last_bounds: tuple[float, float, float, float] | None = None  # front window, fractions of the screen

    def _fraction(self, b) -> tuple[float, float, float, float] | None:
        try:
            r = self._quartz.CGDisplayBounds(self._quartz.CGMainDisplayID())
            return _fraction_of(b, r.size.width, r.size.height)
        except Exception:
            return None

    def foreground(self) -> tuple[str, str]:
        """Owner of the frontmost layer-0 window. NSWorkspace.frontmostApplication() is NOT used first: in a
        process without a run loop (our daemon) it stays frozen on whatever was frontmost at startup."""
        if self._ws is None:
            return self._osascript()
        try:
            q = self._quartz
            windows = list(
                q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements, q.kCGNullWindowID)
                or []
            )
            front = [w for w in windows if w.get("kCGWindowLayer", 0) == 0 and w.get("kCGWindowOwnerName")]
            if front:
                pid = front[0].get("kCGWindowOwnerPID")
                name = str(front[0]["kCGWindowOwnerName"])
                title = next((str(w.get("kCGWindowName")) for w in front if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowName")), "")
                own = [w for w in front if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowBounds")]
                main = max(own, key=lambda w: float(w["kCGWindowBounds"]["Width"]) * float(w["kCGWindowBounds"]["Height"]), default=None)
                self.last_bounds = self._fraction(main["kCGWindowBounds"]) if main else None
                return name, title
            app = self._ws.frontmostApplication()
            return str(app.localizedName() or ""), ""
        except Exception as exc:  # pragma: no cover
            log.debug("Quartz foreground failed: %s", exc)
            return self._osascript()

    @staticmethod
    def _osascript() -> tuple[str, str]:
        script = (
            'tell application "System Events"\n'
            " set p to first application process whose frontmost is true\n"
            " set n to name of p\n"
            ' set t to ""\n'
            " try\n  set t to name of front window of p\n end try\n"
            ' return n & "\n" & t\nend tell'
        )
        try:
            out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2).stdout
            parts = out.rstrip("\n").split("\n", 1)
            return parts[0], parts[1] if len(parts) > 1 else ""
        except Exception:
            return "", ""


def _fraction_of(b, sw: float, sh: float) -> tuple[float, float, float, float] | None:
    try:
        x, y, w, h = float(b["X"]), float(b["Y"]), float(b["Width"]), float(b["Height"])
    except Exception:
        return None
    if sw <= 0 or sh <= 0 or w <= 0 or h <= 0:
        return None
    x0, y0 = max(0.0, x / sw), max(0.0, y / sh)
    x1, y1 = min(1.0, (x + w) / sw), min(1.0, (y + h) / sh)
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


class X11Foreground:
    def __init__(self):
        self._xdotool = shutil.which("xdotool")

    def foreground(self) -> tuple[str, str]:
        if not self._xdotool:
            return "", ""
        try:
            wid = subprocess.run([self._xdotool, "getactivewindow"], capture_output=True, text=True, timeout=1).stdout.strip()
            if not wid:
                return "", ""
            title = subprocess.run([self._xdotool, "getwindowname", wid], capture_output=True, text=True, timeout=1).stdout.strip()
            pid = subprocess.run([self._xdotool, "getwindowpid", wid], capture_output=True, text=True, timeout=1).stdout.strip()
            app = ""
            if pid:
                try:
                    app = open(f"/proc/{pid}/comm").read().strip()
                except OSError:
                    pass
            return app, title
        except Exception:
            return "", ""


def build_foreground():
    system = platform.system()
    if system == "Darwin":
        return MacForeground()
    if system == "Linux":
        return X11Foreground()
    return StaticForeground()
