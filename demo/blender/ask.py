"""Double-tap Shift, then type the request into the Undo prompt (Unicode key events, keyboard-layout independent).
Refuses to start unless Blender is frontmost, and stops typing if the focus moves to another app."""
import random, sys, time
import Quartz
from AppKit import NSWorkspace
REQ = ("Earlier I deleted the pool and the deck instead of hiding them. "
       "Put them back exactly as they were, without losing the carport, the trees or anything I've done since.")
def post(e): Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
def mark(n): print(f"MARK {n} {time.time():.3f}", flush=True)
front = NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
if front != "Blender":
    print("REFUSED front", front); sys.exit(3)
for code in (56, 59, 58, 55):  # release shift/ctrl/opt/cmd
    e = Quartz.CGEventCreateKeyboardEvent(None, code, False); Quartz.CGEventSetType(e, Quartz.kCGEventFlagsChanged); Quartz.CGEventSetFlags(e, 0); post(e)
time.sleep(0.3)
for _ in range(2):
    for down in (True, False):
        e = Quartz.CGEventCreateKeyboardEvent(None, 56, down); Quartz.CGEventSetFlags(e, Quartz.kCGEventFlagMaskShift if down else 0)
        Quartz.CGEventSetType(e, Quartz.kCGEventFlagsChanged); post(e); time.sleep(0.07)
mark("hotkey")
time.sleep(2.0)
ws = NSWorkspace.sharedWorkspace()
for ch in REQ:
    if ws.frontmostApplication().localizedName() in ("Claude", "Terminal", "Safari", "Brave Browser"):
        print("ABORT typing: focus moved to", ws.frontmostApplication().localizedName()); sys.exit(4)
    for down in (True, False):
        e = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
        Quartz.CGEventKeyboardSetUnicodeString(e, len(ch.encode("utf-16-le")) // 2, ch); Quartz.CGEventSetFlags(e, 0); post(e)
    time.sleep(0.03 + random.uniform(0, 0.025) + (0.1 if ch in ".,;" else 0))
time.sleep(0.6)
for down in (True, False):
    e = Quartz.CGEventCreateKeyboardEvent(None, 36, down); Quartz.CGEventSetFlags(e, 0); post(e); time.sleep(0.03)
mark("submitted")
