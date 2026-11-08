"""The pointer while Undo acts: the macOS arrow with its colours swapped and a small glass label takes the place of the system one, so you can see who
is moving it. The label looks like the bubble (undo.ui.hud_mac): light Liquid Glass, dark text, the pulsing dot of the "executing" state.

It lives in the glow process (undo.ui.glow), which runs exactly as long as the agent acts. It is only a picture that follows
the real pointer: the agent still moves and clicks with the real one. The window is click-through and, like the glow, hidden
from screen captures unless `capturable` is set, so Holo never sees it."""
from __future__ import annotations

import ctypes

from undo.ui.hud_mac import COLORS, make_glass

LABEL = "Undo"
W, H = 130, 80  # room for the arrow, the label and the glass's own shadow (it would be cut into a square otherwise)
TIP = (18, 30)  # the arrow's tip in the window, from its top left corner: it sits exactly on the real pointer
PILL_AT = (18, -1)  # top left corner of the label, from the tip: right next to the arrow
PILL_H = 20
DOT = 6


def _hide_system_pointer() -> bool:
    """A background app can only hide the pointer with this private connection property. Undone by _show_system_pointer,
    and by macOS when the process ends, whatever the reason: the pointer cannot stay hidden. False if it did not work
    (the white arrow sits on top of the system one and covers it)."""
    try:
        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        key = cf.CFStringCreateWithCString(None, b"SetsCursorInBackground", 0x08000100)  # kCFStringEncodingUTF8
        true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        cg._CGSDefaultConnection.restype = ctypes.c_int
        cg.CGSSetConnectionProperty.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        conn = cg._CGSDefaultConnection()
        cg.CGSSetConnectionProperty(conn, conn, key, true)
        return cg.CGDisplayHideCursor(cg.CGMainDisplayID()) == 0
    except (OSError, AttributeError, ValueError):
        return False


def _show_system_pointer() -> None:
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGDisplayShowCursor(cg.CGMainDisplayID())


def _inverted_mac_arrow(AppKit):
    """The real macOS arrow (same shape, same size) with its colours swapped: white with a black outline. Its soft shadow
    stays black. Returns the image and its hot spot, from the image's top left corner."""
    import numpy as np

    cursor = AppKit.NSCursor.arrowCursor()
    size, hot = cursor.image().size(), cursor.hotSpot()
    scale = 2
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, int(size.width * scale), int(size.height * scale), 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
    rep.setSize_(size)
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    cursor.image().drawInRect_(AppKit.NSMakeRect(0, 0, size.width, size.height))
    AppKit.NSGraphicsContext.restoreGraphicsState()

    pixels = np.frombuffer(rep.bitmapData(), dtype=np.uint8).reshape(rep.pixelsHigh(), rep.pixelsWide(), 4)
    alpha = pixels[..., 3:].astype(np.float32) / 255
    rgb = np.divide(pixels[..., :3].astype(np.float32) / 255, alpha, out=np.zeros((*alpha.shape[:2], 3), np.float32), where=alpha > 0)  # premultiplied
    grey = rgb.mean(axis=2, keepdims=True)
    swapped = np.where(alpha >= 0.85, 1 - grey, np.where(grey > 0.5, 0.0, grey))  # see-through dark pixels are the shadow: unchanged
    pixels[..., :3] = np.clip(swapped * alpha * 255, 0, 255).astype(np.uint8)

    image = AppKit.NSImage.alloc().initWithSize_(size)
    image.addRepresentation_(rep)
    return image, (hot.x, hot.y)


def _label(AppKit, parent) -> None:
    """The glass capsule: the pulsing dot and the name, as in the bubble."""
    import Quartz

    text = AppKit.NSTextField.labelWithString_(LABEL)
    text.setFont_(AppKit.NSFont.systemFontOfSize_weight_(11.5, AppKit.NSFontWeightSemibold))
    text.setTextColor_(AppKit.NSColor.colorWithWhite_alpha_(0.0, 0.88))
    text.sizeToFit()
    tw, th = text.frame().size.width, text.frame().size.height
    pill_w = 8 + DOT + 5 + tw + 9
    x, y = TIP[0] + PILL_AT[0], H - (TIP[1] + PILL_AT[1]) - PILL_H

    pill = make_glass(AppKit, pill_w, PILL_H, radius=PILL_H / 2, blur_radius=PILL_H / 2)
    pill.setFrameOrigin_(AppKit.NSMakePoint(x, y))
    parent.addSubview_(pill)

    r, g, b = COLORS["executing"]
    dot = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(x + 8, y + (PILL_H - DOT) / 2, DOT, DOT))
    dot.setWantsLayer_(True)
    dot.layer().setCornerRadius_(DOT / 2)
    dot.layer().setBackgroundColor_(AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0).CGColor())
    pulse = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")  # the rhythm of the bubble's dot
    pulse.setFromValue_(0.55)
    pulse.setToValue_(1.0)
    pulse.setDuration_(0.63)
    pulse.setAutoreverses_(True)
    pulse.setRepeatCount_(1e9)
    dot.layer().addAnimation_forKey_(pulse, "pulse")
    parent.addSubview_(dot)

    text.setFrameOrigin_(AppKit.NSMakePoint(x + 8 + DOT + 5, y + (PILL_H - th) / 2))
    parent.addSubview_(text)


class AgentCursor:
    def __init__(self, AppKit, capturable: bool = False):
        self.AppKit = AppKit

        class AgentCursorPanel(AppKit.NSPanel):  # real Liquid Glass needs the active appearance, in a window that is never key
            def canBecomeKeyWindow(self):
                return False

            def canBecomeMainWindow(self):
                return False

            def _hasActiveAppearanceIgnoringKeyFocus(self):
                return True

            def _hasActiveAppearance(self):
                return True

        win = AgentCursorPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(0, 0, W, H), AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        win.setOpaque_(False)
        win.setBackgroundColor_(AppKit.NSColor.clearColor())
        win.setLevel_(AppKit.NSScreenSaverWindowLevel + 1)
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(False)
        win.setHidesOnDeactivate_(False)
        if not capturable:
            win.setSharingType_(AppKit.NSWindowSharingNone)
        win.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorIgnoresCycle
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        root = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, W, H))
        _label(AppKit, root)
        image, hot = _inverted_mac_arrow(AppKit)
        size = image.size()
        arrow = AppKit.NSImageView.alloc().initWithFrame_(AppKit.NSMakeRect(TIP[0] - hot[0], H - (TIP[1] - hot[1]) - size.height, size.width, size.height))
        arrow.setImage_(image)
        arrow.setImageScaling_(AppKit.NSImageScaleNone)
        root.addSubview_(arrow)
        win.setContentView_(root)
        self.win = win
        self._timer = None
        self._hidden = False
        self._last = None

    def _follow(self, _timer=None) -> None:
        p = self.AppKit.NSEvent.mouseLocation()
        if (p.x, p.y) != self._last:
            self._last = (p.x, p.y)
            self.win.setFrameOrigin_(self.AppKit.NSMakePoint(p.x - TIP[0], p.y - (H - TIP[1])))

    def _first_tick(self, timer) -> None:  # the event loop runs: the arrow can be drawn, so the system one can go
        self._follow()
        self.win.orderFrontRegardless()
        self._hidden = _hide_system_pointer()
        timer.invalidate()
        self._timer = self.AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1 / 120, True, self._follow)

    def show(self) -> None:
        self._timer = self.AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.0, False, self._first_tick)

    def hide(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        if self._hidden:
            self._hidden = False
            _show_system_pointer()
        self.win.orderOut_(None)
