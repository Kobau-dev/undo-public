"""Siri-like white edge light while Undo is acting (the status text lives in the HUD, undo.ui.hud_mac).

Runs as its own process (`python -m undo.ui.glow`) so AppKit owns the main thread; commands arrive on stdin:
  quit             fade out and exit
Look: three conic gradients rotating in opposite directions behind soft distance-to-edge masks (exponential
falloff, rounded corners, no hard edge), so the colours flow around the screen and bleed inwards; it breathes.
The window is click-through, on every Space, above everything and excluded from screen captures (sharingType
none) so Holo never sees it. `--capturable` or UNDO_HUD_CAPTURABLE=1 keeps it visible to screen captures (debug, demo takes).
The agent's pointer (undo.ui.agent_cursor) lives here too: same lifetime."""
from __future__ import annotations

import math
import os
import sys
import threading

# Apple Intelligence palette
PALETTE = [  # white light whose brightness travels around the edges (r, g, b, alpha)
    (1.0, 1.0, 1.0, 1.0),
    (1.0, 1.0, 1.0, 0.30),
    (1.0, 1.0, 1.0, 0.85),
    (1.0, 1.0, 1.0, 0.20),
    (1.0, 1.0, 1.0, 0.70),
    (1.0, 1.0, 1.0, 0.25),
    (1.0, 1.0, 1.0, 1.0),  # seamless conic
]
RADIUS = 12.0  # follows the screen's own corner radius


def main() -> None:
    import AppKit  # type: ignore
    import Quartz  # type: ignore
    from PyObjCTools import AppHelper  # type: ignore

    from undo.ui.agent_cursor import AgentCursor

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    capturable = "--capturable" in sys.argv or os.environ.get("UNDO_HUD_CAPTURABLE") == "1"
    try:
        cursor = AgentCursor(AppKit, capturable)
        cursor.show()
    except Exception:  # the system pointer simply stays
        cursor = None
    frame = AppKit.NSScreen.mainScreen().frame()
    W, H = frame.size.width, frame.size.height
    win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False
    )
    win.setOpaque_(False)
    win.setBackgroundColor_(AppKit.NSColor.clearColor())
    win.setLevel_(AppKit.NSScreenSaverWindowLevel)
    win.setIgnoresMouseEvents_(True)
    win.setHasShadow_(False)
    if not capturable:
        win.setSharingType_(AppKit.NSWindowSharingNone)
    win.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    view = win.contentView()
    view.setWantsLayer_(True)
    root = view.layer()

    def cg(r, g, b, a=1.0):
        return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a).CGColor()

    def forever(key: str, **kw):
        a = Quartz.CABasicAnimation.animationWithKeyPath_(key)
        for k, v in kw.items():
            getattr(a, "set" + k[0].upper() + k[1:] + "_")(v)
        a.setRepeatCount_(1e9)
        a.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(Quartz.kCAMediaTimingFunctionLinear))
        return a

    def soft_mask(falloff: float, corner: float = RADIUS) -> Quartz.CALayer:
        """Alpha = smooth falloff with the distance to the screen border (rounded corners): no hard edge anywhere."""
        import io

        import numpy as np
        from PIL import Image

        step = 3.0  # compute at 1/3 resolution, Core Animation scales it up smoothly
        w, h = int(W / step), int(H / step)
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        xs, ys = (xs + 0.5) * step, (ys + 0.5) * step
        dx, dy = np.minimum(xs, W - xs), np.minimum(ys, H - ys)
        d = np.minimum(dx, dy)
        c = (dx < corner) & (dy < corner)
        d[c] = np.maximum(0.0, corner - np.hypot(corner - dx[c], corner - dy[c]))
        alpha = np.exp(-((d / falloff) ** 1.5))
        img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        img.putalpha(Image.fromarray((alpha * 255).astype(np.uint8), "L"))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        data = AppKit.NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
        m = Quartz.CALayer.layer()
        m.setFrame_(((0, 0), (W, H)))
        m.setContents_(AppKit.NSImage.alloc().initWithData_(data))
        m.setContentsGravity_(Quartz.kCAGravityResize)
        return m

    def conic(rotation_period: float, reverse: bool, phase: float) -> Quartz.CAGradientLayer:
        side = math.hypot(W, H) * 1.05  # big enough to cover the screen while rotating
        g = Quartz.CAGradientLayer.layer()
        g.setType_(Quartz.kCAGradientLayerConic)
        g.setFrame_((((W - side) / 2, (H - side) / 2), (side, side)))
        g.setColors_([cg(*c) for c in PALETTE])
        g.setStartPoint_((0.5, 0.5))
        g.setEndPoint_((0.5 + 0.5 * math.cos(phase), 0.5 + 0.5 * math.sin(phase)))
        turn = -2 * math.pi if reverse else 2 * math.pi
        g.addAnimation_forKey_(forever("transform.rotation.z", fromValue=0.0, toValue=turn, duration=rotation_period), "spin")
        return g

    def glow_layer(falloff: float, opacity: float, period: float, reverse: bool, phase: float, breathe: float):
        container = Quartz.CALayer.layer()
        container.setFrame_(((0, 0), (W, H)))
        container.addSublayer_(conic(period, reverse, phase))
        container.setMask_(soft_mask(falloff))
        container.setOpacity_(opacity)
        b = forever("opacity", fromValue=opacity * breathe, toValue=opacity, duration=1.6 + period / 10)
        b.setAutoreverses_(True)
        b.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(Quartz.kCAMediaTimingFunctionEaseInEaseOut))
        container.addAnimation_forKey_(b, "breathe")
        return container

    glow = Quartz.CALayer.layer()
    glow.setFrame_(((0, 0), (W, H)))
    glow.addSublayer_(glow_layer(falloff=18, opacity=0.35, period=6.0, reverse=False, phase=1.3, breathe=0.6))  # soft halo
    glow.addSublayer_(glow_layer(falloff=6, opacity=0.9, period=4.0, reverse=False, phase=0.0, breathe=0.8))  # thin bright line

    # white highlights sliding along the edges
    edge = Quartz.CGPathCreateWithRoundedRect(((0, 0), (W, H)), RADIUS, RADIUS, None)
    blobs = Quartz.CALayer.layer()
    blobs.setFrame_(((0, 0), (W, H)))
    blobs.setMask_(soft_mask(10))
    for i, (period, size) in enumerate([(3.6, 380), (5.0, 300), (4.3, 340)]):
        blob = Quartz.CAGradientLayer.layer()
        blob.setType_(Quartz.kCAGradientLayerRadial)
        blob.setBounds_(((0, 0), (size, size)))
        blob.setColors_([cg(1, 1, 1, 1.0), cg(1, 1, 1, 0.0)])
        blob.setStartPoint_((0.5, 0.5))
        blob.setEndPoint_((1.0, 1.0))
        move = Quartz.CAKeyframeAnimation.animationWithKeyPath_("position")
        move.setPath_(edge)
        move.setCalculationMode_(Quartz.kCAAnimationPaced)
        move.setDuration_(period * 2)
        move.setRepeatCount_(1e9)
        move.setTimeOffset_(period * 2 * i / 3)
        blob.addAnimation_forKey_(move, "move")
        pulse = forever("opacity", fromValue=0.3, toValue=1.0, duration=period / 3)
        pulse.setAutoreverses_(True)
        blob.addAnimation_forKey_(pulse, "pulse")
        blobs.addSublayer_(blob)
    glow.addSublayer_(blobs)
    root.addSublayer_(glow)


    # fade in
    root.setOpacity_(0.0)
    win.orderFrontRegardless()
    Quartz.CATransaction.begin()
    Quartz.CATransaction.setAnimationDuration_(0.6)
    root.setOpacity_(1.0)
    Quartz.CATransaction.commit()

    def fade_out_and_quit() -> None:
        if cursor:
            cursor.hide()
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setAnimationDuration_(0.45)
        root.setOpacity_(0.0)
        Quartz.CATransaction.commit()
        AppHelper.callLater(0.5, lambda: app.terminate_(None))

    def reader() -> None:
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line == "quit":
                break
        AppHelper.callAfter(fade_out_and_quit)  # "quit" or parent died (stdin closed)

    threading.Thread(target=reader, daemon=True).start()
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
