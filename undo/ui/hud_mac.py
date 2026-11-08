"""Native macOS status panel (child process of `undo run`): listening with mic level + live transcript, thinking, acting, done.
Reads JSON commands on stdin, writes {"typed": ...} / {"esc": true} on stdout. Hidden from screen captures."""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from undo.i18n import t

W, H = 560, 112
H_COMPACT = 76
GLASS_M = 30  # room around the glass for its own shadow (see the back window)
ANIM_S = 0.42  # bubble resize (field shown/hidden), with a slight liquid overshoot
INPUT_STATES = {"listening", "transcribing", "asking"}  # the text box is up: nothing is sent until Enter
COLORS = {
    "listening": (1.0, 0.22, 0.37), "transcribing": (1.0, 0.22, 0.37), "heard": (0.75, 0.35, 0.95),
    "analyzing": (0.75, 0.35, 0.95), "understood": (0.04, 0.52, 1.0), "executing": (0.04, 0.52, 1.0),
    "done": (0.19, 0.82, 0.35), "failed": (1.0, 0.27, 0.23), "stopped": (1.0, 0.62, 0.04), "idle": (0.6, 0.6, 0.6),
}
STOPPABLE = {"listening", "asking", "transcribing", "heard", "analyzing", "understood", "executing"}  # Esc quits: always say so
TITLES = {
    "listening": "Listening…", "transcribing": "Transcribing…", "heard": "Got it",
    "analyzing": "Thinking…", "understood": "I know what to do", "executing": "Working on it…",
    "done": "Done", "failed": "Failed", "stopped": "Stopped", "idle": "Undo is ready",
}
AUTO_HIDE = {"done": 6.0, "failed": 8.0, "stopped": 4.0, "idle": 3.0}
NBARS = 7


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def make_glass(AppKit, w: float = W, h: float = H, radius: float = 26, blur_radius: float = 20):
    """Light Liquid Glass (NSGlassEffectView, macOS 26+) with a white tint so dark text stays legible over busy pages
    (the clear style let the text behind show through); blur fallback before 26."""
    import objc

    frame = AppKit.NSMakeRect(0, 0, w, h)
    light = AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua)
    try:
        glass = objc.lookUpClass("NSGlassEffectView").alloc().initWithFrame_(frame)
        glass.setCornerRadius_(radius)
        glass.setAppearance_(light)
        glass.setTintColor_(AppKit.NSColor.colorWithWhite_alpha_(1.0, 0.6))
        glass.setContentView_(AppKit.NSView.alloc().initWithFrame_(frame))
        return glass
    except objc.error:
        blur = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
        blur.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
        blur.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        blur.setState_(AppKit.NSVisualEffectStateActive)
        blur.setAppearance_(light)
        blur.setWantsLayer_(True)
        blur.layer().setCornerRadius_(blur_radius)
        blur.layer().setMasksToBounds_(True)
        return blur



def _spring(k: float) -> float:
    """Ease-out with a small overshoot (easeOutBack), for the Liquid Glass resize."""
    c1 = 1.1
    return 1 + (c1 + 1) * (k - 1) ** 3 + c1 * (k - 1) ** 2


def _bottom_y(AppKit) -> float:
    """Bottom of the bubble: above the Dock, including a hidden one (auto-hide, full-screen apps) that slides up."""
    scr = AppKit.NSScreen.mainScreen()
    f, v = scr.frame(), scr.visibleFrame()
    dock = v.origin.y - f.origin.y
    try:
        d = AppKit.NSUserDefaults.alloc().initWithSuiteName_("com.apple.dock")
        if (d.stringForKey_("orientation") or "bottom") == "bottom":
            tile = d.floatForKey_("tilesize") or 48.0
            if d.boolForKey_("magnification"):
                tile = max(tile, d.floatForKey_("largesize") or tile)
            dock = max(dock, tile + 20)
    except Exception:
        pass
    return f.origin.y + max(70.0, dock + 16)

def main() -> None:
    import AppKit
    from Foundation import NSObject
    from PyObjCTools import AppHelper

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    class KeyPanel(AppKit.NSPanel):
        def canBecomeKeyWindow(self):
            return True

    class GlassPanel(AppKit.NSPanel):  # Liquid Glass turns near-black in the key window: keep it in one that never is
        def canBecomeKeyWindow(self):
            return False

        def canBecomeMainWindow(self):
            return False

        # AppKit draws real (refracting) Liquid Glass only in windows with the active appearance; a window that never
        # becomes key gets the flat frosted fallback. These private NSWindow hooks make it render the active glass.
        def _hasActiveAppearanceIgnoringKeyFocus(self):
            return True

        def _hasActiveAppearance(self):
            return True

    st = {"h": H, "state": "idle", "text": "", "transcript": "", "steps": [], "level": 0.0, "shown": 0.0, "hide_at": 0.0, "t0": time.time(), "bars": [0.0] * NBARS, "warn_until": 0.0, "edited": False}

    scr = AppKit.NSScreen.mainScreen().frame()
    panel = KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect((scr.size.width - W) / 2, _bottom_y(AppKit), W, H), AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
    panel.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua))  # light text field on light glass
    panel.setOpaque_(False)
    panel.setBackgroundColor_(AppKit.NSColor.clearColor())
    panel.setLevel_(AppKit.NSStatusWindowLevel)
    panel.setHasShadow_(False)  # the glass draws its own edge; a window shadow showed square corners when key
    panel.setHidesOnDeactivate_(False)  # stay visible while the agent brings the target app to the front
    panel.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary)
    if os.environ.get("UNDO_HUD_CAPTURABLE") != "1":
        panel.setSharingType_(AppKit.NSWindowSharingNone)

    back = GlassPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        panel.frame(), AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
    for prop in ("Opaque", "HasShadow"):
        getattr(back, f"set{prop}_")(False)
    back.setBackgroundColor_(AppKit.NSColor.clearColor())
    back.setLevel_(AppKit.NSStatusWindowLevel)
    back.setHidesOnDeactivate_(False)
    back.setIgnoresMouseEvents_(True)
    back.setCollectionBehavior_(panel.collectionBehavior())
    back.setSharingType_(panel.sharingType())
    # The glass draws its own soft shadow around the shape: the back window is larger than the glass (GLASS_M on each
    # side) so that shadow fades out instead of being cut into a square at the window edge.
    holder = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, W + 2 * GLASS_M, H + 2 * GLASS_M))
    container = make_glass(AppKit)
    container.setFrameOrigin_(AppKit.NSMakePoint(GLASS_M, GLASS_M))
    holder.addSubview_(container)
    back.setContentView_(holder)
    root = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, W, H))
    panel.setContentView_(root)

    def sync_back() -> None:
        back.setFrame_display_(AppKit.NSInsetRect(panel.frame(), -GLASS_M, -GLASS_M), True)

    def hide_all() -> None:
        panel.orderOut_(None)
        back.orderOut_(None)

    def front() -> None:
        sync_back()
        back.orderFrontRegardless()
        panel.orderFrontRegardless()

    def color(rgb, a=1.0):
        return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], a)

    dot = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(20, H - 34, 14, 14))
    dot.setWantsLayer_(True)
    dot.layer().setCornerRadius_(7)
    root.addSubview_(dot)

    title = AppKit.NSTextField.labelWithString_("")
    title.setFrame_(AppKit.NSMakeRect(44, H - 40, 360, 24))
    title.setFont_(AppKit.NSFont.systemFontOfSize_weight_(16, AppKit.NSFontWeightSemibold))
    title.setTextColor_(AppKit.NSColor.colorWithWhite_alpha_(0.0, 0.88))
    root.addSubview_(title)

    bars = []
    for i in range(NBARS):
        b = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(W - 24 - (NBARS - i) * 9, H - 40, 5, 4))
        b.setWantsLayer_(True)
        b.layer().setCornerRadius_(2.5)
        root.addSubview_(b)
        bars.append(b)

    body = AppKit.NSTextField.labelWithString_("")
    body.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
    body.setFont_(AppKit.NSFont.systemFontOfSize_(14))
    body.setTextColor_(AppKit.NSColor.colorWithWhite_alpha_(0.0, 0.68))
    root.addSubview_(body)

    hint = AppKit.NSTextField.labelWithString_(t("Esc to quit"))
    hint.setFont_(AppKit.NSFont.systemFontOfSize_weight_(12, AppKit.NSFontWeightMedium))
    hint.setAlignment_(AppKit.NSTextAlignmentRight)
    root.addSubview_(hint)

    field = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(20, 14, W - 40, 32))
    field.setFont_(AppKit.NSFont.systemFontOfSize_(16))
    field.setPlaceholderString_(t("Or type here…"))
    field.setBezelStyle_(AppKit.NSTextFieldRoundedBezel)
    field.setFocusRingType_(AppKit.NSFocusRingTypeNone)
    field.cell().setUsesSingleLineMode_(True)  # a pasted multi-line request stays one line

    def cursor_to_end() -> None:
        editor = field.currentEditor()
        if editor is not None:
            end = AppKit.NSMakeRange(len(str(editor.string()).encode("utf-16-le")) // 2, 0)
            editor.setSelectedRange_(end)
            editor.scrollRangeToVisible_(end)

    def set_field(text: str) -> None:
        editor = field.currentEditor()
        if editor is not None:  # setStringValue_ would end the editing, and the next keystrokes would go nowhere
            editor.setString_(text)
            cursor_to_end()
        else:
            field.setStringValue_(text)

    class Target(NSObject):
        def submit_(self, sender):
            text = " ".join(str(sender.stringValue()).split())
            if text:
                emit({"typed": text})
                sender.setStringValue_("")
                st["transcript"] = text
                render()

        def controlTextDidChange_(self, _note):  # the user's own keystrokes: the transcript stops writing in the field
            if not st["edited"]:
                st["edited"] = True
                emit({"editing": True})

    target = Target.alloc().init()
    field.setTarget_(target)
    field.setAction_("submit:")
    field.setDelegate_(target)
    root.addSubview_(field)

    def on_key(event):
        if event.keyCode() == 53:
            emit({"esc": True})
            hide_all()
            return None
        return event

    AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(AppKit.NSEventMaskKeyDown, on_key)

    def first_line(text: str) -> str:
        return (text or "").strip().split("\n")[0][:120]

    def layout(h: float) -> None:
        f = panel.frame()
        panel.setFrame_display_(AppKit.NSMakeRect(f.origin.x, f.origin.y, W, h), True)
        sync_back()
        container.setFrame_(AppKit.NSMakeRect(GLASS_M, GLASS_M, W, h))
        root.setFrame_(AppKit.NSMakeRect(0, 0, W, h))
        st["h"] = h
        dot.setFrame_(AppKit.NSMakeRect(20, h - 31, 12, 12))
        title.setFrame_(AppKit.NSMakeRect(42, h - 37, 340, 24))

    def apply(p: float) -> None:
        """p = 0 compact bubble, 1 bubble with the text field (values past 1 during the overshoot)."""
        st["p"] = p
        a = min(max(p, 0.0), 1.0)
        layout(H_COMPACT + (H - H_COMPACT) * p)
        body.setFrame_(AppKit.NSMakeRect(20, 12 + 40 * a, st.get("body_w", W - 40), 22))
        hint.setFrame_(AppKit.NSMakeRect(W - 190, 14 + 40 * a, 170, 18))  # on the text line, above the field when there is one
        field.setAlphaValue_(a * a)
        field.setHidden_(a < 0.02)

    def animate_to(target: float) -> None:
        anim = st.get("anim")
        if anim is not None and st.get("p_target") == target:
            return
        if anim is not None:
            anim.invalidate()
            st["anim"] = None
        st["p_target"] = target
        start = st.get("p", target)
        if not panel.isVisible() or start == target:
            apply(target)
            return
        t0 = time.time()

        def step(timer):
            k = min((time.time() - t0) / ANIM_S, 1.0)
            apply(start + (target - start) * _spring(k))
            if k >= 1.0:
                timer.invalidate()
                st["anim"] = None
                apply(target)

        st["anim"] = AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1 / 60, True, step)

    def render():
        s = st["state"]
        asking = s in INPUT_STATES
        title.setStringValue_(st.get("title") or t(TITLES.get(s, s)))
        if asking:
            line = ""  # what was said is in the text field
        elif s == "executing":
            line = st["steps"][-1] if st["steps"] else ""
        elif s == "idle":
            line = ""
        else:
            line = first_line(st["text"])
        acting = s == "executing"
        warned = time.time() < st["warn_until"]
        if acting and not line:
            line = t("Hands off, I'm on it")
        body.setStringValue_(line)
        stoppable = s in STOPPABLE
        st["body_w"] = W - 40 - (170 if stoppable else 0)
        hint.setHidden_(not stoppable)
        hint.setStringValue_(t("Hands off · Esc") if warned else t("Esc to quit"))
        hint.setTextColor_(color(COLORS["failed"]) if warned else AppKit.NSColor.colorWithWhite_alpha_(0.0, 0.45))
        animate_to(1.0 if asking else 0.0)
        apply(st.get("p", 0.0))
        panel.setIgnoresMouseEvents_(not asking)

    def show(state: str, text: str = "", title_text: str | None = None):
        prev = st["state"]
        if prev in {"idle", "done", "failed", "stopped"} or not panel.isVisible():
            sf = AppKit.NSScreen.mainScreen().frame()
            panel.setFrameOrigin_(AppKit.NSMakePoint(sf.origin.x + (sf.size.width - W) / 2, _bottom_y(AppKit)))
            sync_back()
        st.update(state=state, text=text, title=title_text)
        if (state == "listening" and prev != state) or (state == "asking" and prev not in INPUT_STATES):  # never show a previous request or answer
            st["transcript"] = ""
            st["level"] = 0.0
            st["edited"] = False
            set_field("")
        if state in {"listening", "analyzing", "idle"}:
            st["steps"] = []
        st["hide_at"] = time.time() + AUTO_HIDE[state] if state in AUTO_HIDE else 0.0
        render()
        front()
        if state in {"listening", "asking"}:
            if prev not in INPUT_STATES or not panel.isKeyWindow():  # moving between input states keeps the cursor where it is
                app.activateIgnoringOtherApps_(True)
                panel.makeKeyAndOrderFront_(None)
                panel.makeFirstResponder_(field)
                cursor_to_end()  # becoming first responder selects the whole text: a keystroke would erase it
        elif state not in INPUT_STATES and prev in INPUT_STATES:
            panel.resignKeyWindow()
            app.deactivate()

    def handle(msg: dict):
        cmd = msg.get("cmd")
        if cmd == "state":
            show(msg.get("state", "idle"), msg.get("text", ""))
        elif cmd == "ask":
            show("asking", "", msg.get("text") or t("What do you want back?"))
        elif cmd == "transcript":
            st["transcript"] = msg.get("text", "")
            if not st["edited"] and st["state"] in {"listening", "transcribing"}:
                set_field(st["transcript"])
        elif cmd == "input":  # the final transcript (or None: what the user typed stays): only Enter sends it
            st["level"] = 0.0
            if msg.get("text") is not None and not st["edited"]:
                set_field(msg["text"])
            show("asking", "", t("Press Enter to send"))
        elif cmd == "level":
            st["level"] = float(msg.get("value", 0.0))
        elif cmd == "step":
            st["steps"].append(msg.get("text", ""))
            render()
        elif cmd == "warn":
            st["warn_until"] = time.time() + 1.5
            render()
            AppHelper.callLater(1.6, render)
        elif cmd == "quit":
            app.terminate_(None)

    def tick(_timer):
        now = time.time()
        s = st["state"]
        if st["hide_at"] and now >= st["hide_at"]:
            st["hide_at"] = 0.0
            hide_all()
        rgb = COLORS.get(s, COLORS["idle"])
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 5))
        dot.layer().setBackgroundColor_(color(rgb, pulse if s not in {"done", "failed", "stopped", "idle"} else 1.0).CGColor())
        for i, b in enumerate(bars):
            if s in {"listening", "asking"}:
                lvl = min(1.0, st["level"] * 18)
                target_h = 4 + 16 * lvl * (0.55 + 0.45 * abs(math.sin(now * 9 + i * 1.3)))
            elif s in {"transcribing", "analyzing", "heard", "understood", "executing"}:
                target_h = 4 + 10 * (0.5 + 0.5 * math.sin(now * 6 - i * 0.7))
            else:
                target_h = 4
            st["bars"][i] += (target_h - st["bars"][i]) * 0.35
            h = st["bars"][i]
            b.setFrame_(AppKit.NSMakeRect(W - 24 - (NBARS - i) * 9, st["h"] - 25 - h / 2, 5, h))
            b.layer().setBackgroundColor_(color(rgb, 0.9).CGColor())

    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1 / 30, True, tick)

    def stdin_loop():
        for line in sys.stdin:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            AppHelper.callAfter(handle, msg)
        AppHelper.callAfter(app.terminate_, None)

    threading.Thread(target=stdin_loop, daemon=True).start()
    render()
    app.run()


if __name__ == "__main__":
    main()
