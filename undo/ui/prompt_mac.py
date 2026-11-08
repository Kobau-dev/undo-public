"""Native macOS request box shown while Undo listens (Tk windows of a background process stay invisible on macOS).
Usage: python -m undo.ui.prompt_mac "question". Prints the typed request on stdout and exits; Esc exits empty."""
from __future__ import annotations

import sys
from undo.i18n import t


def main() -> None:
    import AppKit
    from Foundation import NSObject

    question = sys.argv[1] if len(sys.argv) > 1 else t("What do you want back?")
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    class KeyPanel(AppKit.NSPanel):
        def canBecomeKeyWindow(self):
            return True

        def cancelOperation_(self, sender):
            AppKit.NSApp.terminate_(None)

    class Target(NSObject):
        def submit_(self, sender):
            text = " ".join(str(sender.stringValue()).split())
            if text:
                sys.stdout.write(text + "\n")
                sys.stdout.flush()
                AppKit.NSApp.terminate_(None)

    W, H = 600, 104
    scr = AppKit.NSScreen.mainScreen().frame()
    rect = AppKit.NSMakeRect((scr.size.width - W) / 2, scr.size.height * 0.70, W, H)
    panel = KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(rect, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(AppKit.NSColor.clearColor())
    panel.setLevel_(AppKit.NSStatusWindowLevel)
    panel.setHasShadow_(True)
    panel.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary)

    blur = AppKit.NSVisualEffectView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, W, H))
    blur.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
    blur.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
    blur.setState_(AppKit.NSVisualEffectStateActive)
    blur.setWantsLayer_(True)
    blur.layer().setCornerRadius_(18)
    blur.layer().setMasksToBounds_(True)
    panel.setContentView_(blur)

    label = AppKit.NSTextField.labelWithString_(t("Undo is listening…  ") + question)
    label.setFrame_(AppKit.NSMakeRect(20, H - 38, W - 40, 22))
    label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(14, AppKit.NSFontWeightSemibold))
    label.setTextColor_(AppKit.NSColor.whiteColor())
    blur.addSubview_(label)

    field = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(20, 18, W - 40, 34))
    field.setFont_(AppKit.NSFont.systemFontOfSize_(17))
    field.setPlaceholderString_(t("Speak, or type your request and press Enter  ·  Esc to close"))
    field.setBezelStyle_(AppKit.NSTextFieldRoundedBezel)
    field.setFocusRingType_(AppKit.NSFocusRingTypeNone)
    field.cell().setUsesSingleLineMode_(True)  # a pasted multi-line request stays one line
    target = Target.alloc().init()
    field.setTarget_(target)
    field.setAction_("submit:")
    blur.addSubview_(field)

    def on_key(event):
        if event.keyCode() == 53:  # Esc
            AppKit.NSApp.terminate_(None)
            return None
        return event

    AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(AppKit.NSEventMaskKeyDown, on_key)
    panel.makeKeyAndOrderFront_(None)
    panel.makeFirstResponder_(field)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
