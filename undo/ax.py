"""macOS Accessibility: read the controls of an app window (label, value, position) and act on them by id.

Used by the recorder (exact form values next to each screenshot) and by the executor (fill / press a control by id,
even off-screen, instead of hunting for it on screenshots). Every function degrades to "nothing" off macOS."""
from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass, field

from undo.log import get_logger

log = get_logger("ax")

FIELD_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}
TOGGLE_ROLES = {"AXRadioButton", "AXCheckBox"}
PRESS_ROLES = {"AXButton", "AXPopUpButton", "AXMenuButton", "AXLink"}
TEXT_ROLES = {"AXStaticText", "AXHeading"}
_PASSWORDISH = ("password", "mot de passe", "passcode", "code secret", "cvv", "cvc", "cryptogramme")
_enabled_pids: set[int] = set()


@dataclass
class Control:
    id: int
    role: str
    label: str
    value: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    el: object = field(default=None, repr=False, compare=False)

    @property
    def kind(self) -> str:
        if self.role in FIELD_ROLES:
            return "field"
        if self.role in TOGGLE_ROLES:
            return "radio" if self.role == "AXRadioButton" else "checkbox"
        if self.role == "AXPopUpButton":
            return "menu"
        if self.role == "AXLink":
            return "link"
        return "button"

    @property
    def checked(self) -> bool:
        return self.value in {"1", "True", "true"}

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def line(self) -> str:
        """For the executor prompt."""
        s = f"#{self.id} {self.kind} «{self.label}»"
        if self.kind == "field":
            s += f" = «{_clip(self.value, 120)}»" if self.value else " (empty)"
        elif self.kind in {"radio", "checkbox"}:
            s += " [x]" if self.checked else " [ ]"
        elif self.kind == "menu" and self.value:
            s += f" = «{_clip(self.value, 60)}»"
        return s

    def state_line(self) -> str | None:
        """For the recorder: only what the user set (filled fields, ticked boxes, chosen menus)."""
        if self.kind == "field" and self.value.strip():
            return f"«{self.label}» = «{_clip(self.value, 2000)}»"
        if self.kind in {"radio", "checkbox"} and self.checked:
            return f"[x] «{self.label}»"
        if self.kind == "menu" and self.value.strip():
            return f"«{self.label}» = «{_clip(self.value, 200)}»"
        return None


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def available() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        import ApplicationServices  # noqa: F401

        return True
    except ImportError:
        return False


def _front_pids() -> list[int]:
    """Owners of on-screen normal windows, frontmost first."""
    try:
        import Quartz

        ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID) or []
        return [int(w["kCGWindowOwnerPID"]) for w in ws if w.get("kCGWindowLayer", 0) == 0 and w.get("kCGWindowOwnerPID")]
    except Exception:
        return []


def _pid(app_name: str) -> int | None:
    """Pid of the app with that name. Several processes can share a name (e.g. "python": Undo, its HUD and an app
    run from a venv): never ourselves, regular apps before accessory ones (HUD, menu bar), then the frontmost."""
    import AppKit

    name = (app_name or "").lower()
    apps = [a for a in AppKit.NSWorkspace.sharedWorkspace().runningApplications() if int(a.processIdentifier()) != os.getpid()]
    for exact in (True, False):
        found = [a for a in apps if (n := (a.localizedName() or "").lower()) and ((n == name) if exact else (name in n or n in name))]
        if len(found) > 1:
            front = _front_pids()
            rank = lambda p: front.index(p) if p in front else len(front)
            found.sort(key=lambda a: (int(a.activationPolicy()) != 0, rank(int(a.processIdentifier()))))
        if found:
            return int(found[0].processIdentifier())
    return _pid_by_title(name)


def _pid_by_title(name: str) -> int | None:
    """The model may name an app by its window title ("Sillage CRM") when the process is called something else."""
    if not name:
        return None
    try:
        import Quartz

        ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID) or []
        for w in ws:
            pid = int(w.get("kCGWindowOwnerPID") or 0)
            if w.get("kCGWindowLayer", 0) == 0 and pid and pid != os.getpid() and name in str(w.get("kCGWindowName") or "").lower():
                return pid
    except Exception:
        pass
    return None


def _get(el, attr):
    from ApplicationServices import AXUIElementCopyAttributeValue

    err, v = AXUIElementCopyAttributeValue(el, attr, None)
    return v if err == 0 else None


def _geom(el) -> tuple[float, float, float, float]:
    from ApplicationServices import AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType

    try:
        ok1, p = AXValueGetValue(_get(el, "AXPosition"), kAXValueCGPointType, None)
        ok2, s = AXValueGetValue(_get(el, "AXSize"), kAXValueCGSizeType, None)
        if ok1 and ok2:
            return float(p.x), float(p.y), float(s.width), float(s.height)
    except Exception:
        pass
    return 0.0, 0.0, 0.0, 0.0


def _label(el, last_text: str) -> str:
    for attr in ("AXTitle", "AXDescription"):
        v = _get(el, attr)
        if v and str(v).strip():
            return _clip(v, 90)
    tui = _get(el, "AXTitleUIElement")
    if tui is not None:
        v = _get(tui, "AXValue") or _get(tui, "AXTitle")
        if v and str(v).strip():
            return _clip(v, 90)
    for attr in ("AXPlaceholderValue", "AXHelp"):
        v = _get(el, attr)
        if v and str(v).strip():
            return _clip(v, 90)
    return _clip(last_text, 90) if last_text else ""


def snapshot(app_name: str, max_nodes: int = 4000, budget: float = 0.8) -> list[Control]:
    """Controls of the app's focused window, in reading order. In a browser, only the page (AXWebArea) is kept.
    Password fields (AXSecureTextField or password-like labels) are never returned."""
    if not available() or not app_name:
        return []
    try:
        from ApplicationServices import AXUIElementCreateApplication, AXUIElementSetAttributeValue

        pid = _pid(app_name)
        if pid is None:
            return []
        app = AXUIElementCreateApplication(pid)
        if pid not in _enabled_pids:  # Chromium/Electron only build the web tree once an AX client asks for it
            AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
            _enabled_pids.add(pid)
        win = _get(app, "AXFocusedWindow") or _get(app, "AXMainWindow")
        if win is None:
            return []
        t0 = time.time()
        seen = 0
        out: list[tuple[bool, Control]] = []
        has_web = False
        last_text = ""

        def walk(el, in_web: bool, depth: int) -> None:
            nonlocal seen, has_web, last_text
            if depth > 90 or seen >= max_nodes or time.time() - t0 > budget:
                return
            seen += 1
            role = _get(el, "AXRole") or ""
            if role == "AXWebArea":
                in_web = has_web = True
            if role in TEXT_ROLES:
                v = _get(el, "AXValue") or _get(el, "AXTitle")
                if v and str(v).strip():
                    last_text = str(v)
            elif role in FIELD_ROLES | TOGGLE_ROLES | PRESS_ROLES:
                label = _label(el, last_text if role in FIELD_ROLES else "")
                if not any(p in label.lower() for p in _PASSWORDISH):
                    val = _get(el, "AXValue")
                    x, y, w, h = _geom(el)
                    out.append((in_web, Control(0, role, label, "" if val is None else str(val), x, y, w, h, el)))
            for ch in _get(el, "AXChildren") or []:
                walk(ch, in_web, depth + 1)

        walk(win, False, 0)
        controls = [c for web, c in out if web or not has_web]
        controls = [c for c in controls if c.label or c.kind == "field"]
        for i, c in enumerate(controls, 1):
            c.id = i
        return controls
    except Exception as exc:
        log.debug("ax snapshot failed for %s: %s", app_name, exc)
        return []


def focused_is_password() -> bool:
    """The focused element is a password field, even in apps that do not turn on macOS secure input (e.g. Qt)."""
    if not available():
        return False
    try:
        from ApplicationServices import AXUIElementCopyAttributeValue, AXUIElementCreateSystemWide

        err, el = AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), "AXFocusedUIElement", None)
        if err or el is None:
            return False

        def attr(name: str):
            e, v = AXUIElementCopyAttributeValue(el, name, None)
            return None if e else v

        if "AXSecureTextField" in (str(attr("AXSubrole")), str(attr("AXRole"))):
            return True
        label = " ".join(str(attr(n) or "") for n in ("AXTitle", "AXDescription", "AXPlaceholderValue", "AXHelp")).lower()
        return any(p in label for p in _PASSWORDISH)
    except Exception:
        return False


def form_state(controls: list[Control]) -> str:
    return "\n".join(s for s in (c.state_line() for c in controls) if s)


def press(c: Control) -> bool:
    from ApplicationServices import AXUIElementPerformAction

    AXUIElementPerformAction(c.el, "AXScrollToVisible")
    return AXUIElementPerformAction(c.el, "AXPress") == 0


def focus(c: Control) -> tuple[float, float] | None:
    """Scroll the control into view and focus it; returns its fresh center (screen points) for a fallback click."""
    from ApplicationServices import AXUIElementPerformAction, AXUIElementSetAttributeValue

    AXUIElementPerformAction(c.el, "AXScrollToVisible")
    time.sleep(0.25)
    AXUIElementSetAttributeValue(c.el, "AXFocused", True)
    x, y, w, h = _geom(c.el)
    return (x + w / 2, y + h / 2) if w and h else None


def value(c: Control) -> str:
    v = _get(c.el, "AXValue")
    return "" if v is None else str(v)
