"""Log the mouse pointer (screen points) and left-button state at 60 Hz until killed.
usage: cursor_log.py out.jsonl   -> lines {"t": epoch, "x": .., "y": .., "down": 0/1}"""
import json, signal, sys, time
import Quartz
out = open(sys.argv[1], "w")
stop = False
def bye(*_):
    global stop
    stop = True
signal.signal(signal.SIGTERM, bye); signal.signal(signal.SIGINT, bye)
while not stop:
    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    down = Quartz.CGEventSourceButtonState(Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGMouseButtonLeft)
    out.write(json.dumps({"t": round(time.time(), 4), "x": round(p.x, 1), "y": round(p.y, 1), "down": int(bool(down))}) + "\n")
    time.sleep(1 / 60)
out.close()
